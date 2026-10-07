"""Anonbench1's Pi adapter, built on Harbor's adapter at the pinned commit.

Harbor's adapter needs three changes for these runs:

- Code mode is on unless the job config turns it off. Pi ships its `codemode` tool
  inactive, so the adapter lists Pi's default tools plus `codemode` with `--tools`.
- A custom endpoint's model entry carries the job config's prices and limits, so Pi
  reports cost, not only tokens.
- Install retries a few times. On 2026-10-06, 3 of the first 14 trials of a GLM job failed
  at install: npm lost its registry connection, or nvm could not fetch the Node index.
  Only the install retries; a failed agent run is never repeated.
"""

import asyncio
from typing import Any, override

from harbor.agents.installed.base import NonZeroAgentExitCodeError
from harbor.agents.installed.pi import Pi, PiOptions
from harbor.agents.model_connection import ResolvedModelConnection
from harbor.environments.base import BaseEnvironment
from pydantic import BaseModel, Field

DEFAULT_TOOLS = ("read", "bash", "edit", "write")
INSTALL_ATTEMPTS = 3
INSTALL_RETRY_DELAY_SEC = 15


class ModelPrice(BaseModel):
    """USD per million tokens."""

    input: float = Field(ge=0)
    output: float = Field(ge=0)
    cache_read: float = Field(ge=0)
    cache_write: float = Field(ge=0)


class Anonbench1PiOptions(PiOptions):
    code_mode: bool = Field(default=True, description="Add Pi's codemode tool.")
    price: ModelPrice | None = Field(default=None, description="Prices for cost reporting.")
    context_window: int | None = Field(default=None, ge=1)
    max_output_tokens: int | None = Field(default=None, ge=1)


class Anonbench1Pi(Pi):
    options_model = Anonbench1PiOptions
    options: Anonbench1PiOptions

    @override
    async def install(self, environment: BaseEnvironment) -> None:
        for attempt in range(1, INSTALL_ATTEMPTS + 1):
            try:
                await super().install(environment)
                return
            except NonZeroAgentExitCodeError:
                if attempt == INSTALL_ATTEMPTS:
                    raise
                self.logger.warning(f"Pi install attempt {attempt} failed; retrying")
                await asyncio.sleep(INSTALL_RETRY_DELAY_SEC * attempt)

    @override
    def build_cli_flags(self) -> str:
        tools = [*DEFAULT_TOOLS, *(["codemode"] if self.options.code_mode else [])]
        return " ".join(
            part for part in (super().build_cli_flags(), f"--tools {','.join(tools)}") if part
        )

    @override
    def _build_custom_models_json(
        self, access: ResolvedModelConnection, model_id: str
    ) -> dict[str, Any] | None:
        models_json = super()._build_custom_models_json(access, model_id)
        if models_json is None:
            return None
        for provider in models_json["providers"].values():
            for model in provider["models"]:
                if self.options.context_window is not None:
                    model["contextWindow"] = self.options.context_window
                if self.options.max_output_tokens is not None:
                    model["maxTokens"] = self.options.max_output_tokens
                if self.options.price is not None:
                    price = self.options.price
                    model["cost"] = {
                        "input": price.input,
                        "output": price.output,
                        "cacheRead": price.cache_read,
                        "cacheWrite": price.cache_write,
                    }
        return models_json
