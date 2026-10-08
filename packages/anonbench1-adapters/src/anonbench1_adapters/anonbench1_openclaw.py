"""Anonbench1's OpenClaw adapter, built on Harbor's adapter at the pinned commit.

This dated copy also pins Node 26.11.1 and OpenClaw 2026.9.8 during installation
and before runtime commands. Provider selection and trajectory capture are inherited.

Harbor's adapter needs seven changes for these runs:

- The runtime is explicit. OpenClaw otherwise picks one itself.
- The run's model is OpenClaw's default and utility model, so side tasks use the same
  model as the agent.
- The run's model is also the PDF and image model. Without these, OpenClaw's PDF tool
  can send the extracted PDF text to a different default model. The image tool falls
  back the same way, so both are bound to this run's model.
- Code mode is on unless the job config turns it off.
- A custom endpoint gets a model entry with the provider's own model ID. Harbor's adapter
  registers the model under its Harbor name, with the provider prefix, which OpenClaw
  cannot resolve.
- That entry asks the stream for usage and carries the job config's prices, so OpenClaw
  reports tokens and cost.
- Install retries a few times. In 8 OpenClaw installs on 2026-10-05, npm reset the
  connection twice. Only the install retries; a failed agent run is never repeated.
"""

import asyncio
from typing import Any, Literal, override

from anonbench1_adapters.anonbench1_pins import NODE_INSTALL, PinnedNodeRuntime, npm_guard, require_version
from harbor.agents.installed.base import NonZeroAgentExitCodeError
from harbor.agents.installed.openclaw import OpenClaw, OpenClawOptions
from harbor.environments.base import BaseEnvironment
from pydantic import BaseModel, Field

INSTALL_ATTEMPTS = 3
INSTALL_RETRY_DELAY_SEC = 15


class ModelPrice(BaseModel):
    """USD per million tokens."""

    input: float = Field(ge=0)
    output: float = Field(ge=0)
    cache_read: float = Field(ge=0)
    cache_write: float = Field(ge=0)


class Anonbench1OpenClawOptions(OpenClawOptions):
    runtime: Literal["openclaw", "codex"] = Field(
        description="OpenClaw agent runtime: codex for OpenAI models, openclaw otherwise."
    )
    code_mode: bool = Field(default=True, description="OpenClaw code mode for this model.")
    model_api: Literal["openai-completions", "openai-responses"] | None = Field(
        default=None, description="Wire API of a custom endpoint."
    )
    price: ModelPrice | None = Field(default=None, description="Prices for cost reporting.")
    context_window: int | None = Field(default=None, ge=1)
    max_output_tokens: int | None = Field(default=None, ge=1)


class Anonbench1OpenClaw(PinnedNodeRuntime, OpenClaw):
    package = "openclaw"
    pinned_version = "2026.9.8"
    executable = "openclaw"
    options_model = Anonbench1OpenClawOptions
    options: Anonbench1OpenClawOptions

    @override
    async def install(self, environment: BaseEnvironment) -> None:
        require_version(self._version, self.pinned_version)
        for attempt in range(1, INSTALL_ATTEMPTS + 1):
            try:
                await self.ensure_system_dependencies(environment, ("curl", "ca_certificates"))
                await self.exec_as_agent(
                    environment,
                    command=(
                        f"{NODE_INSTALL} && npm install -g openclaw@{self.pinned_version} && "
                        'mkdir -p "$HOME/.local/share/harbor/openclaw-atif" && '
                        'npm install --prefix "$HOME/.local/share/harbor/openclaw-atif" '
                        "--save-exact --omit=dev --ignore-scripts @openclaw/openclaw-atif@0.1.4 && "
                        f"{npm_guard(self.package, self.pinned_version)} && openclaw --version"
                    ),
                    timeout_sec=self._install_exec_timeout_sec,
                )
                return
            except NonZeroAgentExitCodeError:
                if attempt == INSTALL_ATTEMPTS:
                    raise
                self.logger.warning(f"OpenClaw install attempt {attempt} failed; retrying")
                await asyncio.sleep(INSTALL_RETRY_DELAY_SEC * attempt)

    @override
    def _build_full_openclaw_config(self) -> dict[str, Any]:
        cfg = super()._build_full_openclaw_config()
        assert self.model_name is not None
        provider, model_id = self.model_name.split("/", 1)
        defaults = cfg.setdefault("agents", {}).setdefault("defaults", {})
        defaults["model"] = {"primary": self.model_name}
        defaults["utilityModel"] = self.model_name
        defaults["pdfModel"] = {"primary": self.model_name}
        defaults["imageModel"] = {"primary": self.model_name}
        agent_models = defaults.setdefault("models", {})
        agent_models[self.model_name] = {
            **agent_models.get(self.model_name, {}),
            "agentRuntime": {"id": self.options.runtime},
            "codeMode": self.options.code_mode,
        }
        endpoint = cfg.get("models", {}).get("providers", {}).get(provider)
        if isinstance(endpoint, dict) and endpoint.get("baseUrl"):
            self._register_endpoint_model(endpoint, model_id)
        return cfg

    def _register_endpoint_model(self, endpoint: dict[str, Any], model_id: str) -> None:
        if self.options.model_api is None:
            raise ValueError("A custom endpoint needs the model_api argument")
        endpoint["api"] = self.options.model_api
        entry: dict[str, Any] = {
            "id": model_id,
            "name": model_id,
            "reasoning": self.options.thinking not in (None, "off"),
            "compat": {"supportsUsageInStreaming": True},
        }
        if self.options.context_window is not None:
            entry["contextWindow"] = self.options.context_window
        if self.options.max_output_tokens is not None:
            entry["maxTokens"] = self.options.max_output_tokens
        if self.options.price is not None:
            price = self.options.price
            entry["cost"] = {
                "input": price.input,
                "output": price.output,
                "cacheRead": price.cache_read,
                "cacheWrite": price.cache_write,
            }
        others = [
            row
            for row in endpoint.get("models", [])
            if row.get("id") not in (model_id, self.model_name)
        ]
        endpoint["models"] = [entry, *others]
