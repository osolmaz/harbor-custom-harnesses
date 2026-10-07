"""ShellBench's OpenClaw adapter, built on Harbor's adapter at the pinned commit.

Harbor's adapter needs seven changes for these runs:

- The runtime is explicit. OpenClaw otherwise picks one itself.
- The run's model is OpenClaw's default and utility model, so side tasks use the same
  model as the agent.
- The run's model is also the PDF and image model. Without these, OpenClaw's PDF tool
  sends the extracted PDF text to OpenClaw's built-in default, gpt-6-astra: in the smoke
  test the HF router rejected that request, so the PDF tool failed, and on an OpenAI
  endpoint a different model would read the PDF. The image tool falls back the same way.
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


class ShellBenchOpenClawOptions(OpenClawOptions):
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


class ShellBenchOpenClaw(OpenClaw):
    options_model = ShellBenchOpenClawOptions
    options: ShellBenchOpenClawOptions

    @override
    async def install(self, environment: BaseEnvironment) -> None:
        for attempt in range(1, INSTALL_ATTEMPTS + 1):
            try:
                await super().install(environment)
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
