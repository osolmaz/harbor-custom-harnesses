"""Tests for the shared install and runtime pins. No inference and no task data."""

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
from harbor.models.task.config import MCPServerConfig

from anonbench1_adapters import anonbench1_openclaw, anonbench1_pi
from anonbench1_adapters.anonbench1_openclaw import Anonbench1OpenClaw
from anonbench1_adapters.anonbench1_pins import (
    NODE_INSTALL,
    NODE_VERSION,
    PinnedNodeRuntime,
    npm_guard,
    require_version,
)
from anonbench1_adapters.attested import Anonbench1OpenClaw as AttestedOpenClaw

MODEL = "openai/zai-org/GLM-5.3-Flash:fireworks-ai"
ENV = {"OPENAI_BASE_URL": "https://router.huggingface.co/v1", "OPENAI_API_KEY": "k"}


def test_require_version_accepts_the_pinned_version() -> None:
    require_version("2026.9.8", "2026.9.8")


def test_require_version_rejects_any_other_version() -> None:
    with pytest.raises(ValueError, match="requires version 2026.9.8; got '2026.9.5'"):
        require_version("2026.9.5", "2026.9.8")


def test_require_version_rejects_a_missing_version() -> None:
    with pytest.raises(ValueError, match="got None"):
        require_version(None, "2026.9.8")


def test_npm_guard_selects_the_pinned_node_and_package_version() -> None:
    guard = npm_guard("openclaw", "2026.9.8")
    assert f"nvm use {NODE_VERSION}" in guard
    assert "npm root -g" in guard
    assert "= 2026.9.8" in guard


def test_pinned_runtime_version_command_checks_the_package_first() -> None:
    stub = PinnedNodeRuntime.__new__(PinnedNodeRuntime)
    stub.package = "openclaw"
    stub.pinned_version = "2026.9.8"
    stub.executable = "openclaw"
    command = PinnedNodeRuntime.get_version_command(stub)
    assert command.endswith(" && openclaw --version")
    assert "npm root -g" in command


def test_node_install_pins_node_26() -> None:
    assert "nvm install 26" in NODE_INSTALL
    assert 'test "$(node --version)" = "v26.11.1"' in NODE_INSTALL


def openclaw(tmp_path: Path, **kwargs: object) -> Anonbench1OpenClaw:
    options = {
        "version": "2026.9.8",
        "runtime": "openclaw",
        "model_api": "openai-completions",
    }
    return Anonbench1OpenClaw(
        logs_dir=tmp_path,
        model_name=MODEL,
        extra_env=ENV,
        **{**options, **kwargs},  # ty: ignore[invalid-argument-type]
    )


async def test_pinned_runtime_translates_the_harbor_node_prefix(
    tmp_path: Path, monkeypatch
) -> None:
    seen: dict[str, str] = {}

    async def record(self, environment, command, **kwargs):  # noqa: ANN001, ANN202
        seen["command"] = command
        return None

    monkeypatch.setattr(anonbench1_openclaw.OpenClaw, "exec_as_agent", record)
    agent = openclaw(tmp_path)
    await agent.exec_as_agent(
        "env", command=". ~/.nvm/nvm.sh && nvm use 22 && openclaw helper"
    )
    assert seen["command"] == npm_guard("openclaw", "2026.9.8") + " && openclaw helper"


async def test_pinned_runtime_leaves_unknown_commands_untouched(
    tmp_path: Path, monkeypatch
) -> None:
    seen: dict[str, str] = {}

    async def record(self, environment, command, **kwargs):  # noqa: ANN001, ANN202
        seen["command"] = command
        return None

    monkeypatch.setattr(anonbench1_openclaw.OpenClaw, "exec_as_agent", record)
    agent = openclaw(tmp_path)
    await agent.exec_as_agent("env", command="echo hello")
    assert seen["command"] == "echo hello"


async def test_pinned_runtime_run_checks_the_version_then_the_guard(
    tmp_path: Path, monkeypatch
) -> None:
    ran = []
    commands: list[str] = []

    async def record_run(self, instruction, environment, context):  # noqa: ANN001, ANN202
        ran.append(instruction)

    async def record_exec(self, environment, command, **kwargs):  # noqa: ANN001, ANN202
        commands.append(command)
        return None

    monkeypatch.setattr(anonbench1_openclaw.OpenClaw, "run", record_run)
    monkeypatch.setattr(anonbench1_openclaw.OpenClaw, "exec_as_agent", record_exec)
    agent = openclaw(tmp_path)
    await agent.run("task", "env", context=None)  # noqa: ARG001
    assert ran == ["task"]
    assert commands == [npm_guard("openclaw", "2026.9.8")]


async def test_pinned_runtime_run_rejects_a_wrong_version(tmp_path: Path) -> None:
    agent = openclaw(tmp_path, version="2026.9.5")
    with pytest.raises(ValueError, match="requires version"):
        await agent.run("task", "env", context=None)  # noqa: ARG001


async def test_openclaw_install_pins_the_package_and_checks_it(tmp_path: Path) -> None:
    agent = openclaw(tmp_path)
    agent.ensure_system_dependencies = AsyncMock()
    agent.exec_as_agent = AsyncMock()
    await agent.install(environment=offline_env())  # ty: ignore[invalid-argument-type]
    command = agent.exec_as_agent.await_args.kwargs["command"]  # ty: ignore[unresolved-attribute]
    assert NODE_INSTALL in command
    assert "npm install -g openclaw@2026.9.8" in command
    assert "openclaw-atif@0.1.4" in command
    assert command.strip().endswith("openclaw --version")


def test_pi_mcp_config_rejects_legacy_sse(tmp_path: Path) -> None:
    agent = pi_agent(tmp_path)
    agent.mcp_servers = [
        MCPServerConfig(
            name="legacy", transport="sse", url="https://example.invalid/sse"
        )
    ]
    with pytest.raises(ValueError, match="legacy SSE"):
        agent._build_mcp_config()


def test_pi_mcp_config_rejects_duplicate_namespaces(tmp_path: Path) -> None:
    agent = pi_agent(tmp_path)
    agent.mcp_servers = [
        MCPServerConfig(name="my-server", transport="stdio", command="x", args=[]),
        MCPServerConfig(name="my_server", transport="stdio", command="y", args=[]),
    ]
    with pytest.raises(ValueError, match="unique namespaces"):
        agent._build_mcp_config()


def test_pi_mcp_config_emits_enabled_direct_servers(tmp_path: Path) -> None:
    agent = pi_agent(tmp_path)
    agent.mcp_servers = [
        MCPServerConfig(
            name="docs", transport="stdio", command="docs-mcp", args=["-v"]
        ),
        MCPServerConfig(
            name="web", transport="streamable-http", url="https://x.invalid"
        ),
    ]
    config = agent._build_mcp_config()
    assert config["mcpServers"]["docs"] == {
        "type": "stdio",
        "command": "docs-mcp",
        "args": ["-v"],
        "enabled": True,
        "exposure": "direct",
    }
    assert config["mcpServers"]["web"]["type"] == "http"


def pi_agent(tmp_path: Path, **kwargs: object) -> anonbench1_pi.Anonbench1Pi:
    options = {"version": "1.1.0", "model_api": "openai-completions"}
    return anonbench1_pi.Anonbench1Pi(
        logs_dir=tmp_path,
        model_name=MODEL,
        extra_env=ENV,
        **{**options, **kwargs},  # ty: ignore[invalid-argument-type]
    )


async def test_pi_install_pins_the_package_and_checks_it(tmp_path: Path) -> None:
    agent = pi_agent(tmp_path)
    agent.ensure_system_dependencies = AsyncMock()
    agent.exec_as_agent = AsyncMock()
    await agent.install(environment=offline_env())  # ty: ignore[invalid-argument-type]
    command = agent.exec_as_agent.await_args.kwargs["command"]  # ty: ignore[unresolved-attribute]
    assert NODE_INSTALL in command
    assert "@earendil-works/pi-coding-agent" in command
    assert 'test "$(pi --version)" = 1.1.0' in command


async def test_pi_run_checks_the_guard_and_streams_the_session(
    tmp_path: Path, monkeypatch
) -> None:
    agent = pi_agent(tmp_path)
    agent.ensure_system_dependencies = AsyncMock()
    agent.exec_as_agent = AsyncMock()
    agent._ensure_config_dir = AsyncMock()
    agent._upload_config_text = AsyncMock()
    agent._write_custom_models_json = AsyncMock(return_value=None)
    agent._write_max_turns_extension = AsyncMock(return_value="max-turns.ts")
    agent._session_positions = AsyncMock(return_value={})
    agent._build_register_skills_command = lambda: None  # ty: ignore[invalid-assignment]
    agent.mcp_servers = []
    monkeypatch.setattr(type(agent), "environment_logs_dir", tmp_path, raising=False)
    await agent.run("do the task", environment=offline_env(), context=None)
    commands = [call.kwargs["command"] for call in agent.exec_as_agent.call_args_list]
    assert any("anonbench1_evidence.mjs" in command for command in commands)
    assert any("--print --mode json" in command for command in commands)
    assert any(npm_guard(agent.package, "1.1.0") in command for command in commands)


def test_pi_evidence_qualification_flags_a_model_mismatch(
    tmp_path: Path, monkeypatch
) -> None:
    agent = pi_agent(tmp_path)
    sessions = tmp_path / "pi" / "sessions"
    sessions.mkdir(parents=True)
    entry = {
        "customType": "anonbench1-provider-evidence",
        "data": {
            "models": [{"requested_model": "x", "observed_model": "someone-else"}],
            "codemode_active": True,
        },
    }
    (sessions / "s1.jsonl").write_text(json.dumps(entry) + "\n")
    (tmp_path / "trajectory.json").write_text(json.dumps({"steps": []}))
    agent._session_usage_start = {}
    monkeypatch.setattr(
        anonbench1_pi.Pi, "populate_context_post_run", lambda self, context: None
    )
    agent.populate_context_post_run(_ContextStub())  # ty: ignore[invalid-argument-type]
    saved = json.loads((tmp_path / "trajectory.json").read_text())
    qualification = saved["final_metrics"]["extra"]["pi_research_evidence"]
    assert qualification["model_mismatch"] is True
    assert qualification["status"] == "failed"


class _ContextStub:
    def __init__(self) -> None:
        self.n_input_tokens = 1
        self.n_cache_tokens = 0
        self.n_output_tokens = 1
        self.cost_usd = 0.0
        self.metadata: dict[str, Any] | None = None


async def test_attested_openclaw_setup_writes_the_attestation_evidence(
    tmp_path: Path, monkeypatch
) -> None:
    async def ok_install(self, environment):  # noqa: ANN001
        return None

    monkeypatch.setattr(Anonbench1OpenClaw, "install", ok_install)
    agent = AttestedOpenClaw(
        logs_dir=tmp_path,
        model_name=MODEL,
        extra_env=ENV,
        version="2026.9.8",
        runtime="openclaw",
        model_api="openai-completions",
    )
    await agent.setup(
        offline_env(  # ty: ignore[invalid-argument-type]
            "Now using node v26.11.0 (npm v11.0.0)\nOpenClaw 2026.9.8 (fc23bc8)\n"
        )
    )
    evidence = json.loads((tmp_path / "attestation.json").read_text())
    assert evidence["attested_version"].endswith("OpenClaw 2026.9.8 (fc23bc8)")
    assert evidence["pinned_version"] == "2026.9.8"


class _AttestEnvironment:
    def __init__(self, stdout: str) -> None:
        self.stdout = stdout

    async def exec(self, command: str, **kwargs: object):
        return _AttestResult(0, self.stdout)


class _AttestResult:
    def __init__(self, return_code: int, stdout: str) -> None:
        self.return_code = return_code
        self.stdout = stdout


class _Policy:
    def __init__(self, network_mode) -> None:
        self.network_mode = network_mode


class _FakeRunEnv:
    """Env double for offline-tools reads; exec and upload are recorded."""

    def __init__(self, stdout: str = "") -> None:
        from harbor.models.task.config import NetworkMode

        self.commands: list[str] = []
        self.stdout = stdout
        self.network_policy = _Policy(NetworkMode.PUBLIC)
        self.task_env_config = _TaskEnv()

    async def exec(self, command: str, **kwargs: object):
        self.commands.append(command)
        return type("R", (), {"return_code": 0, "stdout": self.stdout})()

    def scoped_exec_env(self, _extra):
        import contextlib

        @contextlib.contextmanager
        def _scope():
            yield self

        return _scope()


class _TaskEnv:
    mcp_servers: list[object] = []


def offline_env(stdout: str = "") -> _FakeRunEnv:
    return _FakeRunEnv(stdout)
