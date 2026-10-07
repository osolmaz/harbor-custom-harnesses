"""ShellBench's Hermes adapter, built on Harbor's adapter at the pinned commit.

Harbor's adapter needs five changes for Hermes v2026.9.24:

- Install with the installer from the pinned tag. Harbor downloads it from main, and that
  installer needs a pm/ package that this tag does not have.
- Check the version with `hermes --version`. This release removed `hermes version`.
- Send a custom endpoint chat completions through Hermes's custom provider. Harbor's
  adapter selects the openai-api provider, which uses the Responses API. On that route,
  Hermes recorded 0 tokens in the smoke test; whether the router sent no usage or Hermes
  did not read it was not checked.
- Read tokens from Hermes's usage table, `session_model_usage` in `state.db`. It has one
  row per session, model, and task: the main loop, side calls such as compression and title
  generation, subagent sessions, and the sessions that compression starts. The session
  row that `hermes sessions export` writes leaves out side calls, and the export leaves
  out subagent sessions. The adapter prices the totals with the job config's rates.
- Install retries a few times. One install on 2026-10-05 failed because curl could not
  connect to GitHub. Only the install retries; a failed agent run is never repeated.

Code mode is Hermes's `execute_code` tool. It is part of Hermes's default `hermes-cli`
toolset, which this adapter keeps, so it is on unless the job config turns it off.
"""

import asyncio
import json
import shlex
from typing import Any, Literal, override

import yaml
from harbor.agents.installed.base import NonZeroAgentExitCodeError, with_prompt_template
from harbor.agents.installed.hermes import Hermes, HermesOptions
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext
from pydantic import BaseModel, Field

INSTALLER = "https://raw.githubusercontent.com/NousResearch/hermes-agent/{ref}/scripts/install.sh"
HERMES_HOME = "/tmp/hermes"
SESSION_LOG = "/logs/agent/hermes-session.jsonl"
USAGE_LOG = "/logs/agent/hermes-usage.json"
USAGE_FIELDS = ("input_tokens", "cache_read_tokens", "cache_write_tokens", "output_tokens")
# Runs with Hermes's own Python, next to the hermes launcher in its venv, because the
# task image may have no Python. A failure leaves no usage file, and tokens stay unknown.
DUMP_USAGE = f"""
export PATH="$HOME/.local/bin:$PATH"
py="$(dirname "$(readlink -f "$(command -v hermes)")")/python"
"$py" - > {USAGE_LOG}.tmp << 'PYEOF' && mv {USAGE_LOG}.tmp {USAGE_LOG} || rm -f {USAGE_LOG}.tmp
import json, sqlite3
con = sqlite3.connect("file:{HERMES_HOME}/state.db?mode=ro", uri=True)
con.row_factory = sqlite3.Row
rows = con.execute(
    "SELECT session_id, task, model, billing_provider, SUM(api_call_count) AS api_calls, "
    "SUM(input_tokens) AS input_tokens, SUM(cache_read_tokens) AS cache_read_tokens, "
    "SUM(cache_write_tokens) AS cache_write_tokens, SUM(output_tokens) AS output_tokens "
    "FROM session_model_usage GROUP BY session_id, task, model, billing_provider"
)
print(json.dumps([dict(row) for row in rows]))
PYEOF
"""
API_MODES = {"openai-completions": "chat_completions", "openai-responses": "codex_responses"}
INSTALL_ATTEMPTS = 3
INSTALL_RETRY_DELAY_SEC = 15


class ModelPrice(BaseModel):
    """USD per million tokens."""

    input: float = Field(ge=0)
    output: float = Field(ge=0)
    cache_read: float = Field(ge=0)
    cache_write: float = Field(ge=0)


class ShellBenchHermesOptions(HermesOptions):
    code_mode: bool = Field(default=True, description="Keep Hermes's execute_code tool.")
    model_api: Literal["openai-completions", "openai-responses"] = Field(
        description="Wire API of the custom endpoint."
    )
    price: ModelPrice | None = Field(default=None, description="Prices for cost reporting.")


class ShellBenchHermes(Hermes):
    options_model = ShellBenchHermesOptions
    options: ShellBenchHermesOptions

    @override
    def get_version_command(self) -> str | None:
        return 'export PATH="$HOME/.local/bin:$PATH"; hermes --version'

    @override
    async def install(self, environment: BaseEnvironment) -> None:
        if not self._version:
            raise ValueError("Pin Hermes to a release tag with the version argument")
        for attempt in range(1, INSTALL_ATTEMPTS + 1):
            try:
                await self._install_once(environment)
                return
            except NonZeroAgentExitCodeError:
                if attempt == INSTALL_ATTEMPTS:
                    raise
                self.logger.warning(f"Hermes install attempt {attempt} failed; retrying")
                await asyncio.sleep(INSTALL_RETRY_DELAY_SEC * attempt)

    async def _install_once(self, environment: BaseEnvironment) -> None:
        assert self._version is not None
        await self.ensure_system_dependencies(environment, ("curl", "git", "ripgrep", "xz"))
        await self.exec_as_agent(
            environment,
            command=(
                "set -euo pipefail; "
                f"curl -fsSL {INSTALLER.format(ref=self._version)} "
                f"| bash -s -- --skip-setup --branch {shlex.quote(self._version)} && "
                'export PATH="$HOME/.local/bin:$PATH" && '
                f"mkdir -p {HERMES_HOME}/sessions {HERMES_HOME}/skills {HERMES_HOME}/memories && "
                "hermes --version"
            ),
        )

    def build_config(self) -> dict[str, Any]:
        """Harbor's Hermes config, with the model on a custom chat endpoint."""
        if not self.model_name or "/" not in self.model_name:
            raise ValueError("Model name must be in the format provider/model_name")
        if not self.options.code_mode:
            raise ValueError(
                "This adapter keeps Hermes's default tools, which include execute_code"
            )
        base_url = self._get_env("OPENAI_BASE_URL")
        if not base_url:
            raise ValueError("Set OPENAI_BASE_URL in the agent env")
        config = yaml.safe_load(self._build_config_yaml(self.model_name, self.options.max_turns))
        config.pop("provider", None)
        config["model"] = {
            "provider": "custom",
            "default": self.model_name.split("/", 1)[1],
            "base_url": base_url.rstrip("/"),
            "key_env": "OPENAI_API_KEY",
            "api_mode": API_MODES[self.options.model_api],
        }
        return config

    @with_prompt_template
    @override
    async def run(
        self, instruction: str, environment: BaseEnvironment, context: AgentContext
    ) -> None:
        if self._resume:
            raise RuntimeError("This adapter runs single-step tasks only")
        config_yaml = yaml.safe_dump(self.build_config(), sort_keys=False)
        env = {
            "HERMES_HOME": HERMES_HOME,
            "TERMINAL_ENV": "local",
            "HARBOR_INSTRUCTION": instruction,
        }
        await self.exec_as_agent(
            environment,
            command=f"mkdir -p {HERMES_HOME} && cat > {HERMES_HOME}/config.yaml << 'EOF'\n{config_yaml}EOF",
            env=env,
            timeout_sec=10,
        )
        for command in (
            self._build_register_mcp_servers_command(),
            self._build_register_skills_command(),
        ):
            if command:
                await self.exec_as_agent(environment, command=command, env=env, timeout_sec=10)
        flags = self.build_cli_flags()
        run = (
            'export PATH="$HOME/.local/bin:$PATH" && '
            f'hermes --yolo chat -q "$HARBOR_INSTRUCTION" -Q {flags} '
            "2>&1 | stdbuf -oL tee /logs/agent/hermes.txt"
        )
        try:
            await self.exec_as_agent(environment, command=run, env=env)
        finally:
            await self.exec_as_agent(
                environment,
                command=(
                    'export PATH="$HOME/.local/bin:$PATH" && '
                    f"hermes sessions export {SESSION_LOG} --source oneshot 2>/dev/null || true"
                ),
                env={"HERMES_HOME": HERMES_HOME},
                timeout_sec=30,
            )
            await self.exec_as_agent(environment, command=DUMP_USAGE, timeout_sec=30)

    @override
    def populate_context_post_run(self, context: AgentContext) -> None:
        super().populate_context_post_run(context)
        context.n_input_tokens = context.n_cache_tokens = context.n_output_tokens = None
        context.cost_usd = None
        usage_path = self.logs_dir / "hermes-usage.json"
        if not usage_path.exists():
            self.logger.warning("Hermes usage table was not exported; tokens are unknown")
            return
        try:
            rows = json.loads(usage_path.read_text())
        except json.JSONDecodeError:
            self.logger.warning("Hermes usage table export is not valid JSON; tokens are unknown")
            return
        apply_usage_rows(context, rows, self.options.price)


def apply_usage_rows(
    context: AgentContext, rows: list[dict[str, Any]], price: ModelPrice | None
) -> None:
    """Sum Hermes's usage rows into Harbor's context.

    Hermes keeps uncached input in input_tokens, apart from cache reads and writes. Harbor
    counts all prompt tokens as input and the cache reads among them as cached.
    """
    totals = {field: sum(int(row.get(field) or 0) for row in rows) for field in USAGE_FIELDS}
    uncached = totals["input_tokens"]
    cache_read = totals["cache_read_tokens"]
    cache_write = totals["cache_write_tokens"]
    output = totals["output_tokens"]
    context.n_input_tokens = uncached + cache_read + cache_write
    context.n_cache_tokens = cache_read
    context.n_output_tokens = output
    if price is not None:
        context.cost_usd = (
            uncached * price.input
            + cache_read * price.cache_read
            + cache_write * price.cache_write
            + output * price.output
        ) / 1_000_000
    context.metadata = {
        **(context.metadata or {}),
        "hermes_usage": {
            "sessions": len({row.get("session_id") for row in rows}),
            "api_calls": sum(int(row.get("api_calls") or 0) for row in rows),
            "by_task": {
                (row.get("task") or "main"): {field: row.get(field) for field in USAGE_FIELDS}
                for row in rows
            },
        },
    }
