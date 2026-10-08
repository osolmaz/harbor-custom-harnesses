"""Anonbench1's Pi adapter, built on Harbor's adapter at the pinned commit.

This dated copy reuses the existing Pi adapter. It additionally enforces Pi 1.1.0
and Node 26.11.1 at install and runtime. MCP uses Pi 1.1's built-in extension,
not Harbor's incompatible legacy extension. The run override preserves Harbor's
direct model connection, skill/max-turn registration, session offsets, output and
trajectory accounting. Required servers are checked before the first model turn.
Pi's package supports stdio and streamable HTTP; legacy SSE is not reinterpreted.

The supported stream hook records selective observations in the existing session.
Post-run metadata separates execution from research qualification: returned-model
mismatches fail qualification, and SDK-only zero usage remains unknown. Capture
is partial; requested identity and normalized totals are not upgraded to proof.

The existing run-specific behavior is retained:

- Code mode is on unless the job config turns it off. Pi ships its `codemode` tool
  inactive, so the adapter lists Pi's default tools plus `codemode` with `--tools`.
- A custom endpoint's model entry carries the job config's prices and limits, so Pi
  reports cost, not only tokens.
- Install retries a few times. On 2026-10-06, 3 of the first 14 trials of a job failed
  at install: npm lost its registry connection, or nvm could not fetch the Node index.
  Only the install retries; a failed agent run is never repeated.
"""

import asyncio
import json
import re
import shlex
from pathlib import Path
from typing import Any, override

from anonbench1_adapters.anonbench1_pins import NODE_INSTALL, PinnedNodeRuntime, npm_guard, require_version
from harbor.agents.installed.base import NonZeroAgentExitCodeError, with_prompt_template
from harbor.agents.installed.pi import (
    _CUSTOM_PROVIDER,
    _PI_CONFIG_DIR_ENV,
    _REMOTE_PI_CONFIG_DIR,
    Pi,
    PiOptions,
)
from harbor.agents.model_connection import ResolvedModelConnection
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext
from harbor.utils.trajectory_utils import format_trajectory_json
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


class Anonbench1Pi(PinnedNodeRuntime, Pi):
    package = "@earendil-works/pi-coding-agent"
    pinned_version = "1.1.0"
    executable = "pi"
    options_model = Anonbench1PiOptions
    options: Anonbench1PiOptions

    @override
    async def install(self, environment: BaseEnvironment) -> None:
        require_version(self._version, self.pinned_version)
        self._build_mcp_config()
        for attempt in range(1, INSTALL_ATTEMPTS + 1):
            try:
                await self.ensure_system_dependencies(environment, ("curl",))
                await self.exec_as_agent(
                    environment,
                    command=(
                        f"{NODE_INSTALL} && "
                        f"npm install -g --ignore-scripts {self.package}@{self.pinned_version} && "
                        f"{npm_guard(self.package, self.pinned_version)} && "
                        f'test "$(pi --version)" = {self.pinned_version}'
                    ),
                )
                return
            except NonZeroAgentExitCodeError:
                if attempt == INSTALL_ATTEMPTS:
                    raise
                self.logger.warning(f"Pi install attempt {attempt} failed; retrying")
                await asyncio.sleep(INSTALL_RETRY_DELAY_SEC * attempt)

    @override
    def _build_mcp_config(self) -> dict[str, Any]:
        servers: dict[str, Any] = {}
        namespaces: set[str] = set()
        for server in self.mcp_servers:
            namespace = server.name.replace("-", "_")
            if not re.fullmatch(r"[A-Za-z0-9_-]+", server.name) or namespace in namespaces:
                raise ValueError("Pi MCP server names must be valid and have unique namespaces")
            namespaces.add(namespace)
            if server.transport == "stdio":
                config = {"type": "stdio", "command": server.command, "args": list(server.args)}
            elif server.transport == "streamable-http":
                config = {"type": "http", "url": server.url}
            else:
                raise ValueError(
                    "Pi 1.1.0 built-in MCP does not support legacy SSE; "
                    "a verified stdio or streamable HTTP task contract is required"
                )
            servers[server.name] = {**config, "enabled": True, "exposure": "direct"}
        return {"mcpServers": servers}

    async def _check_required_mcp(self, environment: BaseEnvironment, env: dict[str, str]) -> None:
        result = await self.exec_as_agent(
            environment,
            command=f"{npm_guard(self.package, self.pinned_version)} && pi mcp list --json",
            env=env,
        )
        try:
            report = json.loads(result.stdout)
        except (json.JSONDecodeError, TypeError) as exc:
            raise RuntimeError("Pi MCP readiness did not return JSON") from exc
        rows = report.get("servers") if isinstance(report, dict) else None
        if not isinstance(rows, list) or report.get("errors") != []:
            raise RuntimeError("Pi MCP readiness returned configuration errors")
        for server in self.mcp_servers:
            matches = [
                row for row in rows if isinstance(row, dict) and row.get("name") == server.name
            ]
            if len(matches) != 1:
                raise RuntimeError("A required MCP server is missing or duplicated")
            row = matches[0]
            tools = row.get("tools")
            if (
                row.get("state") != "connected"
                or row.get("enabled") is not True
                or row.get("exposure") != "direct"
                or not isinstance(tools, list)
                or not tools
                or not all(isinstance(tool, str) and tool for tool in tools)
                or row.get("toolExposure")
            ):
                raise RuntimeError("A required MCP server did not expose its tools")

    @override
    @with_prompt_template
    async def run(
        self, instruction: str, environment: BaseEnvironment, context: AgentContext
    ) -> None:
        require_version(self._version, self.pinned_version)
        self._build_mcp_config()
        await self.exec_as_agent(environment, command=npm_guard(self.package, self.pinned_version))
        if not self.model_name or "/" not in self.model_name:
            raise ValueError("Model name must be in the format provider/model_name")
        provider, model_id = self.model_name.split("/", 1)
        access = self.model_connection
        provider = access.provider or provider
        env = dict(access.env)
        if provider == "anthropic" and (token := self._get_env("ANTHROPIC_OAUTH_TOKEN")):
            env["ANTHROPIC_OAUTH_TOKEN"] = token

        models_json = self._build_custom_models_json(access, model_id)
        if models_json is not None or self.mcp_servers:
            env[_PI_CONFIG_DIR_ENV] = _REMOTE_PI_CONFIG_DIR.as_posix()
        if models_json is not None:
            await self._write_custom_models_json(environment, models_json)
            provider = _CUSTOM_PROVIDER

        await self._ensure_config_dir(environment)
        evidence_file = Path(__file__).with_name("anonbench1_evidence.mjs")
        evidence_path = (_REMOTE_PI_CONFIG_DIR / evidence_file.name).as_posix()
        await self._upload_config_text(
            environment,
            content=evidence_file.read_text(),
            remote_path=evidence_path,
            filename=evidence_file.name,
        )
        extensions = [evidence_path]
        if self.mcp_servers:
            await self._write_mcp_config(environment)
            await self._check_required_mcp(environment, env)
            extensions.append("builtin:mcp")
        if self.options.max_turns is not None:
            extensions.append(
                await self._write_max_turns_extension(environment, self.options.max_turns)
            )
        extension_args = "".join(f"--extension {shlex.quote(path)} " for path in extensions)
        skills_command = self._build_register_skills_command()
        if skills_command:
            await self.exec_as_agent(environment, command=skills_command)
        self._session_usage_start = (
            await self._session_positions(environment) if self._resume else {}
        )
        output_path = self.environment_logs_dir / self._OUTPUT_FILENAME
        session_dir = self.environment_logs_dir / self._SESSIONS_DIRECTORY
        await self.exec_as_agent(
            environment,
            command=(
                f"{npm_guard(self.package, self.pinned_version)} && "
                f"mkdir -p {shlex.quote(str(session_dir))} && pi --print --mode json "
                f"--session-dir {shlex.quote(str(session_dir))} "
                f"{'--continue ' if self._resume else ''}"
                f"--provider {shlex.quote(provider)} --model {shlex.quote(model_id)} "
                f"{extension_args}{self.build_cli_flags()} {shlex.quote(instruction)} "
                f'2>&1 </dev/null | grep -v \'"type":"message_update"\' '
                f"| stdbuf -oL tee {shlex.quote(str(output_path))}"
            ),
            env=env,
        )

    @override
    def populate_context_post_run(self, context: AgentContext) -> None:
        super().populate_context_post_run(context)
        expected = (self.model_name or "").split("/", 1)[-1]
        observed: set[str] = set()
        evidence: list[dict[str, Any]] = []
        sessions = list((self.logs_dir / self._SESSIONS_DIRECTORY).glob("*.jsonl"))
        if sessions:
            session = max(sessions, key=lambda path: (path.stat().st_mtime_ns, path.name))
            copied = self._session_usage_start.get(session.name, 0)
            for line in session.read_text().splitlines()[copied:]:
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(entry, dict):
                    continue
                data = entry.get("data")
                if entry.get("customType") == "anonbench1-provider-evidence" and isinstance(
                    data, dict
                ):
                    evidence.append(data)
                    for row in data.get("models", []):
                        if isinstance(row, dict) and isinstance(row.get("observed_model"), str):
                            observed.add(row["observed_model"])
                message = entry.get("message")
                if isinstance(message, dict) and isinstance(message.get("responseModel"), str):
                    observed.add(message["responseModel"])

        mismatch = any(model != expected for model in observed)
        inactive = self.options.code_mode and any(
            row.get("codemode_active") is False for row in evidence
        )
        qualification = {
            "status": "failed" if mismatch or inactive else "unverified",
            "requested_model": expected,
            "observed_models": sorted(observed),
            "model_mismatch": mismatch,
            "provider_identity": "unverified; configured provider is requested metadata",
            "codemode": "inactive-observed"
            if inactive
            else (
                "active-observed"
                if evidence and all(row.get("codemode_active") is True for row in evidence)
                else "unverified"
            ),
            "usage": "partial-raw-observations"
            if any(row.get("usage") for row in evidence)
            else "unverified",
            "complete_call_accounting": False,
            "execution_completion_is_research_qualification": False,
        }
        context.metadata = {**(context.metadata or {}), "pi_research_evidence": qualification}
        # Pi initializes usage to zero even when the provider omits usage. Raw zero
        # observations remain in the session; they do not establish aggregate zeros.
        unknown_zero = all(
            value in (None, 0)
            for value in (
                context.n_input_tokens,
                context.n_output_tokens,
                context.n_cache_tokens,
                context.cost_usd,
            )
        )
        if unknown_zero:
            context.n_input_tokens = context.n_output_tokens = context.n_cache_tokens = None
            context.cost_usd = None
        trajectory_path = self.logs_dir / self._TRAJECTORY_FILENAME
        if trajectory_path.exists():
            trajectory = json.loads(trajectory_path.read_text())
            final = trajectory.setdefault("final_metrics", {})
            final.setdefault("extra", {})["pi_research_evidence"] = qualification
            if unknown_zero:
                for field in (
                    "total_prompt_tokens",
                    "total_completion_tokens",
                    "total_cached_tokens",
                    "total_cost_usd",
                ):
                    final[field] = None
            for step in trajectory.get("steps", []):
                metrics = step.get("metrics")
                if metrics and all(
                    metrics.get(field) in (None, 0)
                    for field in ("prompt_tokens", "completion_tokens", "cached_tokens", "cost_usd")
                ):
                    step["metrics"] = None
            trajectory_path.write_text(format_trajectory_json(trajectory))

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
