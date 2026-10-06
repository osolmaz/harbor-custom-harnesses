import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from harbor_hermes_acp import launcher

MODEL = "deepseek-ai/DeepSeek-V4.1-Flash:novita"


class FakeCommands:
    """Records install steps; ``uv venv`` creates the ACP entry point."""

    def __init__(self, head: str = launcher.HERMES_COMMIT, entry: bool = True) -> None:
        self.head = head
        self.entry = entry
        self.calls: list[tuple[list[str], dict[str, str] | None, Path | None]] = []

    def run(
        self, args: Sequence[str], env: Mapping[str, str] | None, cwd: Path | None
    ) -> None:
        self.calls.append((list(args), None if env is None else dict(env), cwd))
        if args[1:2] == ["venv"] and self.entry:
            entry = Path(args[-1]) / "bin" / "hermes-acp"
            entry.parent.mkdir(parents=True)
            entry.touch()

    def read(self, args: Sequence[str]) -> str:
        assert list(args[-2:]) == ["rev-parse", "HEAD"]
        return self.head


def test_requested_model_strips_the_openai_route() -> None:
    env = {"HARBOR_ACP_REQUESTED_MODEL": f"openai/{MODEL}"}
    assert launcher.requested_model(env) == MODEL


@pytest.mark.parametrize(
    "value",
    [
        "",
        MODEL,
        f"anthropic/{MODEL}",
        "openai/deepseek-ai/DeepSeek-V4.1-Flash",
        "openai/DeepSeek:novita",
        "openai/deepseek-ai/DeepSeek-V4.1-Flash:",
    ],
)
def test_requested_model_needs_a_routed_hf_model(value: str) -> None:
    with pytest.raises(ValueError, match="explicit OpenAI-compatible HF model"):
        launcher.requested_model({"HARBOR_ACP_REQUESTED_MODEL": value})


@pytest.mark.parametrize("url", ["", launcher.ROUTER, f"{launcher.ROUTER}/"])
def test_check_endpoint_accepts_the_router(url: str) -> None:
    launcher.check_endpoint({"OPENAI_BASE_URL": url, "OPENAI_API_KEY": "key"})


def test_check_endpoint_rejects_other_endpoints() -> None:
    env = {"OPENAI_BASE_URL": "https://example.com/v1", "OPENAI_API_KEY": "key"}
    with pytest.raises(ValueError, match="endpoint is not supported"):
        launcher.check_endpoint(env)


def test_check_endpoint_needs_a_credential() -> None:
    with pytest.raises(ValueError, match="OPENAI_API_KEY is required"):
        launcher.check_endpoint({})


def test_hermes_config_pins_the_router_model() -> None:
    assert launcher.hermes_config(MODEL) == (
        f'model:\n  provider: huggingface\n  default: "{MODEL}"\n'
    )


def test_child_env_moves_the_credential_to_hf_token(tmp_path: Path) -> None:
    env = {"OPENAI_API_KEY": "key", "OPENAI_BASE_URL": launcher.ROUTER, "PATH": "/bin"}
    assert launcher.child_env(env, tmp_path) == {
        "PATH": "/bin",
        "HF_TOKEN": "key",
        "HERMES_HOME": str(tmp_path),
    }


def test_install_uses_the_release_lockfile(tmp_path: Path) -> None:
    commands = FakeCommands()
    entry = launcher.install(tmp_path, commands.run, commands.read)
    assert entry == tmp_path / "venv" / "bin" / "hermes-acp"
    clone, venv, sync = commands.calls
    assert clone[0] == [
        "git",
        "clone",
        "--depth",
        "1",
        "--branch",
        launcher.HERMES_TAG,
        launcher.HERMES_REPO,
        str(tmp_path / "hermes-agent"),
    ]
    assert venv[0][1:] == ["venv", "--python", "3.11", str(tmp_path / "venv")]
    assert sync[0][1:] == ["sync", "--extra", "all", "--locked"]
    assert sync[2] == tmp_path / "hermes-agent"
    assert sync[1] is not None
    assert sync[1]["UV_PROJECT_ENVIRONMENT"] == str(tmp_path / "venv")


def test_install_reuses_an_existing_install(tmp_path: Path) -> None:
    entry = tmp_path / "venv" / "bin" / "hermes-acp"
    entry.parent.mkdir(parents=True)
    entry.touch()
    commands = FakeCommands()
    assert launcher.install(tmp_path, commands.run, commands.read) == entry
    assert commands.calls == []


def test_install_rejects_a_moved_tag(tmp_path: Path) -> None:
    commands = FakeCommands(head="0" * 40)
    with pytest.raises(RuntimeError, match="not f97608f1"):
        launcher.install(tmp_path, commands.run, commands.read)
    assert len(commands.calls) == 1


def test_install_needs_the_acp_entry_point(tmp_path: Path) -> None:
    commands = FakeCommands(entry=False)
    with pytest.raises(RuntimeError, match="no hermes-acp entry point"):
        launcher.install(tmp_path, commands.run, commands.read)


def test_save_sessions_copies_records_without_links(tmp_path: Path) -> None:
    home = tmp_path / "home"
    (home / "sessions" / "a").mkdir(parents=True)
    (home / "sessions" / "a" / "s.json").write_text("{}")
    (home / "sessions" / "link.json").symlink_to(home / "sessions" / "a" / "s.json")
    (home / "state.db").write_text("db")
    (home / "config.yaml").write_text("model: {}")
    dest = tmp_path / "logs"
    launcher.save_sessions(home, dest)
    copied = sorted(
        p.relative_to(dest).as_posix() for p in dest.rglob("*") if p.is_file()
    )
    assert copied == ["sessions/a/s.json", "state.db"]
    assert not any(p.is_symlink() for p in dest.rglob("*"))


def test_run_logged_sends_output_to_stderr(capfd: pytest.CaptureFixture[str]) -> None:
    launcher.run_logged(["sh", "-c", "echo out"], None, None)
    captured = capfd.readouterr()
    assert captured.out == ""
    assert captured.err == "out\n"


def test_read_output_strips_text() -> None:
    assert launcher.read_output(["sh", "-c", "echo ' value '"]) == "value"


def test_main_rejects_an_unsupported_request(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HARBOR_ACP_REQUESTED_MODEL", raising=False)
    with pytest.raises(SystemExit, match="explicit OpenAI-compatible HF model"):
        launcher.main()


def test_main_runs_hermes_acp_and_saves_sessions(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("HARBOR_ACP_REQUESTED_MODEL", f"openai/{MODEL}")
    monkeypatch.setenv("OPENAI_API_KEY", "key")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    logs = tmp_path / "logs"
    logs.mkdir()
    monkeypatch.setattr(launcher, "AGENT_LOGS", logs)
    entry = tmp_path / "hermes-acp"
    monkeypatch.setattr(launcher, "install", lambda root: entry)
    seen: list[tuple[list[str], dict[str, str]]] = []

    def fake_run(
        args: list[str], env: dict[str, str]
    ) -> subprocess.CompletedProcess[str]:
        seen.append((args, env))
        (Path(env["HERMES_HOME"]) / "state.db").write_text("db")
        return subprocess.CompletedProcess(args, 3)

    monkeypatch.setattr(launcher.subprocess, "run", fake_run)
    with pytest.raises(SystemExit) as exit_info:
        launcher.main()
    assert exit_info.value.code == 3
    args, env = seen[0]
    assert args == [str(entry)]
    home = Path(env["HERMES_HOME"])
    assert home == tmp_path / ".harbor-hermes" / launcher.HERMES_COMMIT / "home"
    assert (home / "config.yaml").read_text() == launcher.hermes_config(MODEL)
    assert env["HF_TOKEN"] == "key"
    assert (logs / "hermes" / "state.db").read_text() == "db"
