"""Unit tests for the Anonbench1 adapters. No inference and no task data."""

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from harbor.agents.installed.base import (
    NetworkConnectionError,
    NonZeroAgentExitCodeError,
)
from harbor.models.agent.context import AgentContext

from anonbench1_adapters import anonbench1_hermes, anonbench1_openclaw, anonbench1_pi
from anonbench1_adapters.anonbench1_hermes import (
    Anonbench1Hermes,
    ModelPrice,
    apply_usage_rows,
)
from anonbench1_adapters.anonbench1_openclaw import Anonbench1OpenClaw
from anonbench1_adapters.anonbench1_pi import Anonbench1Pi
from anonbench1_adapters.attested import (
    Anonbench1Hermes as AttestedHermes,
)
from anonbench1_adapters.attested import (
    Anonbench1OpenClaw as AttestedOpenClaw,
)
from anonbench1_adapters.attested import (
    Anonbench1Pi as AttestedPi,
)

MODEL = "openai/zai-org/GLM-5.3-Flash:fireworks-ai"
MODEL_ID = "zai-org/GLM-5.3-Flash:fireworks-ai"
ROUTER = "https://router.huggingface.co/v1"
ENV = {"OPENAI_BASE_URL": ROUTER, "OPENAI_API_KEY": "test-key"}
PRICE = {"input": 0.15, "output": 0.5, "cache_read": 0.03, "cache_write": 0.15}


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


def test_openclaw_requires_an_explicit_runtime(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="runtime: Field required"):
        Anonbench1OpenClaw(
            logs_dir=tmp_path, model_name=MODEL, extra_env=ENV, version="2026.9.8"
        )


def test_openclaw_pins_runtime_and_code_mode_on_the_model_entry(tmp_path: Path) -> None:
    config = openclaw(tmp_path)._build_full_openclaw_config()
    assert config["agents"]["defaults"]["models"][MODEL] == {
        "agentRuntime": {"id": "openclaw"},
        "codeMode": True,
    }


def test_openclaw_makes_the_run_model_the_default(tmp_path: Path) -> None:
    config = openclaw(tmp_path)._build_full_openclaw_config()
    assert config["agents"]["defaults"]["model"] == {"primary": MODEL}
    assert config["agents"]["defaults"]["utilityModel"] == MODEL
    assert config["agents"]["defaults"]["pdfModel"] == {"primary": MODEL}
    assert config["agents"]["defaults"]["imageModel"] == {"primary": MODEL}


def test_openclaw_code_mode_can_be_turned_off(tmp_path: Path) -> None:
    config = openclaw(tmp_path, code_mode=False)._build_full_openclaw_config()
    assert config["agents"]["defaults"]["models"][MODEL]["codeMode"] is False


def test_openclaw_registers_the_endpoint_model_with_usage_and_price(
    tmp_path: Path,
) -> None:
    agent = openclaw(
        tmp_path,
        thinking="ultra",
        price=PRICE,
        context_window=1048576,
        max_output_tokens=32768,
    )
    provider = agent._build_full_openclaw_config()["models"]["providers"]["openai"]
    assert provider["baseUrl"] == ROUTER
    assert provider["api"] == "openai-completions"
    assert provider["models"] == [
        {
            "id": MODEL_ID,
            "name": MODEL_ID,
            "reasoning": True,
            "compat": {"supportsUsageInStreaming": True},
            "contextWindow": 1048576,
            "maxTokens": 32768,
            "cost": {
                "input": 0.15,
                "output": 0.5,
                "cacheRead": 0.03,
                "cacheWrite": 0.15,
            },
        }
    ]


def test_openclaw_endpoint_needs_a_model_api(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="model_api"):
        openclaw(tmp_path, model_api=None)._build_full_openclaw_config()


def pi(tmp_path: Path, **kwargs: object) -> Anonbench1Pi:
    options = {"version": "1.0.2", "model_api": "openai-completions"}
    return Anonbench1Pi(
        logs_dir=tmp_path,
        model_name=MODEL,
        extra_env=ENV,
        **{**options, **kwargs},  # ty: ignore[invalid-argument-type]
    )


def test_pi_turns_codemode_on_by_default(tmp_path: Path) -> None:
    assert pi(tmp_path, thinking="high").build_cli_flags() == (
        "--thinking high --tools read,bash,edit,write,codemode"
    )


def test_pi_codemode_can_be_turned_off(tmp_path: Path) -> None:
    assert (
        pi(tmp_path, code_mode=False).build_cli_flags()
        == "--tools read,bash,edit,write"
    )


async def test_pi_install_retries_a_network_failure(
    tmp_path: Path, monkeypatch
) -> None:
    calls = []

    async def flaky_install(self, environment):
        calls.append(environment)
        if len(calls) < 2:
            raise NetworkConnectionError("npm error network")

    monkeypatch.setattr(anonbench1_pi.Pi, "install", flaky_install)
    monkeypatch.setattr(anonbench1_pi, "INSTALL_RETRY_DELAY_SEC", 0)
    await pi(tmp_path).install(environment="env")  # ty: ignore[invalid-argument-type]
    assert len(calls) == 2


def test_pi_endpoint_model_carries_price_and_limits(tmp_path: Path) -> None:
    agent = pi(tmp_path, price=PRICE, context_window=1048576, max_output_tokens=32768)
    models_json = agent._build_custom_models_json(agent.model_connection, MODEL_ID)
    assert models_json is not None
    [provider] = models_json["providers"].values()
    [model] = provider["models"]
    assert model["id"] == MODEL_ID
    assert model["contextWindow"] == 1048576
    assert model["maxTokens"] == 32768
    assert model["cost"] == {
        "input": 0.15,
        "output": 0.5,
        "cacheRead": 0.03,
        "cacheWrite": 0.15,
    }


def hermes(tmp_path: Path, **kwargs: object) -> Anonbench1Hermes:
    options = {"version": "v2026.9.24", "model_api": "openai-completions"}
    return Anonbench1Hermes(
        logs_dir=tmp_path,
        model_name=MODEL,
        extra_env=ENV,
        **{**options, **kwargs},  # ty: ignore[invalid-argument-type]
    )


def test_hermes_uses_the_custom_chat_endpoint(tmp_path: Path) -> None:
    config = hermes(tmp_path).build_config()
    assert "provider" not in config
    assert config["model"] == {
        "provider": "custom",
        "default": MODEL_ID,
        "base_url": ROUTER,
        "key_env": "OPENAI_API_KEY",
        "api_mode": "chat_completions",
    }
    assert config["toolsets"] == ["hermes-cli"]


def test_hermes_refuses_to_drop_code_mode(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="execute_code"):
        hermes(tmp_path, code_mode=False).build_config()


def test_hermes_checks_version_with_the_current_flag(tmp_path: Path) -> None:
    assert hermes(tmp_path).get_version_command().endswith("hermes --version")  # ty: ignore[unresolved-attribute]


async def test_hermes_installs_from_the_pinned_tag(tmp_path: Path) -> None:
    agent = hermes(tmp_path)
    agent.ensure_system_dependencies = AsyncMock()
    agent.exec_as_agent = AsyncMock()
    await agent.install(environment=AsyncMock())
    command = agent.exec_as_agent.await_args.kwargs["command"]  # ty: ignore[unresolved-attribute]
    assert "hermes-agent/v2026.9.24/scripts/install.sh" in command
    assert "/main/" not in command
    assert "--branch v2026.9.24" in command


def test_hermes_counts_main_side_and_subagent_calls() -> None:
    context = AgentContext()
    rows = [
        {
            "session_id": "main",
            "task": "",
            "api_calls": 9,
            "input_tokens": 1000,
            "cache_read_tokens": 3000,
            "cache_write_tokens": 0,
            "output_tokens": 200,
        },
        {
            "session_id": "main",
            "task": "title_generation",
            "api_calls": 1,
            "input_tokens": 50,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
            "output_tokens": 10,
        },
        {
            "session_id": "child",
            "task": "",
            "api_calls": 2,
            "input_tokens": 400,
            "cache_read_tokens": 100,
            "cache_write_tokens": 20,
            "output_tokens": 40,
        },
    ]
    apply_usage_rows(context, rows, ModelPrice(**PRICE))
    assert context.n_input_tokens == 1450 + 3100 + 20
    assert context.n_cache_tokens == 3100
    assert context.n_output_tokens == 250
    expected = (1450 * 0.15 + 3100 * 0.03 + 20 * 0.15 + 250 * 0.5) / 1e6
    assert context.cost_usd == pytest.approx(expected)
    assert context.metadata["hermes_usage"]["sessions"] == 2  # ty: ignore[not-subscriptable]
    assert context.metadata["hermes_usage"]["api_calls"] == 12  # ty: ignore[not-subscriptable]


def test_hermes_reports_unknown_tokens_without_the_usage_table(tmp_path: Path) -> None:
    context = AgentContext(n_input_tokens=5, n_output_tokens=5)
    hermes(tmp_path).populate_context_post_run(context)
    assert context.n_input_tokens is None
    assert context.n_output_tokens is None


async def test_openclaw_install_retries_then_succeeds(
    tmp_path: Path, monkeypatch
) -> None:
    calls = []

    async def flaky_install(self, environment):
        calls.append(environment)
        if len(calls) < 3:
            raise NonZeroAgentExitCodeError("npm error code ECONNRESET")

    monkeypatch.setattr(anonbench1_openclaw.OpenClaw, "install", flaky_install)
    monkeypatch.setattr(anonbench1_openclaw, "INSTALL_RETRY_DELAY_SEC", 0)
    await openclaw(tmp_path).install(environment="env")  # ty: ignore[invalid-argument-type]
    assert len(calls) == 3


async def test_openclaw_install_gives_up_after_three_attempts(
    tmp_path: Path, monkeypatch
) -> None:
    async def broken_install(self, environment):
        raise NonZeroAgentExitCodeError("npm error code ECONNRESET")

    monkeypatch.setattr(anonbench1_openclaw.OpenClaw, "install", broken_install)
    monkeypatch.setattr(anonbench1_openclaw, "INSTALL_RETRY_DELAY_SEC", 0)
    with pytest.raises(NonZeroAgentExitCodeError):
        await openclaw(tmp_path).install(environment="env")  # ty: ignore[invalid-argument-type]


async def test_hermes_install_retries_a_network_failure(
    tmp_path: Path, monkeypatch
) -> None:
    agent = hermes(tmp_path)
    agent.ensure_system_dependencies = AsyncMock()
    agent.exec_as_agent = AsyncMock(
        side_effect=[NetworkConnectionError("curl: (7)"), None]
    )
    monkeypatch.setattr(anonbench1_hermes, "INSTALL_RETRY_DELAY_SEC", 0)
    await agent.install(environment=AsyncMock())
    assert agent.exec_as_agent.await_count == 2


class AttestResult:
    def __init__(self, return_code: int = 0, stdout: str = "") -> None:
        self.return_code = return_code
        self.stdout = stdout


class AttestEnvironment:
    """Fake environment: every command succeeds and prints the given version."""

    def __init__(self, stdout: str) -> None:
        self.stdout = stdout

    async def exec(self, command: str, **kwargs: object) -> AttestResult:
        return AttestResult(0, self.stdout)


async def test_pi_setup_attests_the_installed_version(
    tmp_path: Path, monkeypatch
) -> None:
    async def ok_install(self, environment):
        return None

    monkeypatch.setattr(anonbench1_pi.Pi, "install", ok_install)
    agent = AttestedPi(
        logs_dir=tmp_path,
        model_name=MODEL,
        extra_env=ENV,
        version="1.0.2",
        model_api="openai-completions",
    )
    await agent.setup(AttestEnvironment("1.0.2\n"))  # ty: ignore[invalid-argument-type]
    evidence = json.loads((tmp_path / "attestation.json").read_text())
    assert evidence["attested_version"] == "1.0.2"


async def test_hermes_setup_attests_the_installed_version(
    tmp_path: Path, monkeypatch
) -> None:
    agent = AttestedHermes(
        logs_dir=tmp_path,
        model_name=MODEL,
        extra_env=ENV,
        version="v2026.9.24",
        model_api="openai-completions",
    )
    agent.ensure_system_dependencies = AsyncMock()
    agent.exec_as_agent = AsyncMock()
    await agent.setup(AttestEnvironment("v2026.9.24\n"))  # ty: ignore[invalid-argument-type]
    evidence = json.loads((tmp_path / "attestation.json").read_text())
    assert evidence["attested_version"] == "v2026.9.24"


async def test_openclaw_setup_fails_on_a_wrong_installed_version(
    tmp_path: Path, monkeypatch
) -> None:
    async def ok_install(self, environment):
        return None

    monkeypatch.setattr(anonbench1_openclaw.OpenClaw, "install", ok_install)
    agent = AttestedOpenClaw(
        logs_dir=tmp_path,
        model_name=MODEL,
        extra_env=ENV,
        version="2026.9.8",
        runtime="openclaw",
        model_api="openai-completions",
    )
    with pytest.raises(RuntimeError, match="attested version .* != pinned"):
        await agent.setup(AttestEnvironment("2026.9.5\n"))  # ty: ignore[invalid-argument-type]


async def test_hermes_run_writes_the_config_and_exports_usage(
    tmp_path: Path,
) -> None:
    agent = hermes(tmp_path)
    agent.ensure_system_dependencies = AsyncMock()
    agent.exec_as_agent = AsyncMock()
    await agent.run("do the task", environment=AsyncMock(), context=AgentContext())
    commands = [call.kwargs["command"] for call in agent.exec_as_agent.call_args_list]
    assert any("config.yaml" in command for command in commands)
    assert any("hermes --yolo chat" in command for command in commands)
    assert any("hermes sessions export" in command for command in commands)
    assert any("session_model_usage" in command for command in commands)
