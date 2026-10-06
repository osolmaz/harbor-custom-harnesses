"""Install the pinned Hermes release and serve its native ACP agent to Harbor.

Hermes builds no wheel; its release installs from a checkout with the release's own
uv lockfile. This launcher repeats those steps for one pinned commit, configures the
Hugging Face router route that Harbor requested, and runs ``hermes-acp`` on the
inherited standard streams. Install output goes to standard error, because standard
output carries the ACP messages.
"""

import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from uv import find_uv_bin

HERMES_REPO = "https://github.com/NousResearch/hermes-agent.git"
HERMES_TAG = "v2026.9.24"
HERMES_COMMIT = "f97608f178d1ffeca59860195ab7da295f7c8e5f"
# The release installer creates its environment with this Python.
HERMES_PYTHON = "3.11"
ROUTER = "https://router.huggingface.co/v1"
AGENT_LOGS = Path("/logs/agent")
SESSION_RECORDS = ("sessions", "state.db", "state.db-wal", "state.db-shm")

Run = Callable[[Sequence[str], Mapping[str, str] | None, Path | None], None]
Read = Callable[[Sequence[str]], str]


def requested_model(env: Mapping[str, str]) -> str:
    """Return the routed ``model:provider`` that Harbor requested."""
    route, slash, model = env.get("HARBOR_ACP_REQUESTED_MODEL", "").partition("/")
    name, colon, provider = model.rpartition(":")
    if route != "openai" or not slash or not colon or "/" not in name or not provider:
        raise ValueError("Use an explicit OpenAI-compatible HF model and provider")
    return model


def check_endpoint(env: Mapping[str, str]) -> None:
    """Accept only the Hugging Face router with a credential."""
    if (env.get("OPENAI_BASE_URL", "").rstrip("/") or ROUTER) != ROUTER:
        raise ValueError("The configured inference endpoint is not supported")
    if not env.get("OPENAI_API_KEY"):
        raise ValueError("OPENAI_API_KEY is required")


def hermes_config(model: str) -> str:
    """Hermes configuration that pins the router model; JSON strings are YAML."""
    return f"model:\n  provider: huggingface\n  default: {json.dumps(model)}\n"


def child_env(env: Mapping[str, str], home: Path) -> dict[str, str]:
    """Hermes reads the router credential from HF_TOKEN; drop other routes."""
    child = {
        key: value
        for key, value in env.items()
        if key not in ("OPENAI_API_KEY", "OPENAI_BASE_URL")
    }
    child["HF_TOKEN"] = env["OPENAI_API_KEY"]
    child["HERMES_HOME"] = str(home)
    return child


def run_logged(
    args: Sequence[str], env: Mapping[str, str] | None, cwd: Path | None
) -> None:
    subprocess.run(
        list(args),
        env=None if env is None else dict(env),
        cwd=cwd,
        stdout=sys.stderr,
        check=True,
    )


def read_output(args: Sequence[str]) -> str:
    return subprocess.run(
        list(args), capture_output=True, text=True, check=True
    ).stdout.strip()


def install(root: Path, run: Run = run_logged, read: Read = read_output) -> Path:
    """Install the pinned release once and return its ACP entry point."""
    checkout = root / "hermes-agent"
    venv = root / "venv"
    entry = venv / "bin" / "hermes-acp"
    if entry.exists():
        return entry
    run(
        [
            "git",
            "clone",
            "--depth",
            "1",
            "--branch",
            HERMES_TAG,
            HERMES_REPO,
            str(checkout),
        ],
        None,
        None,
    )
    head = read(["git", "-C", str(checkout), "rev-parse", "HEAD"])
    if head != HERMES_COMMIT:
        raise RuntimeError(f"{HERMES_TAG} resolved to {head}, not {HERMES_COMMIT}")
    uv = find_uv_bin()
    run([uv, "venv", "--python", HERMES_PYTHON, str(venv)], None, None)
    sync_env = {
        **os.environ,
        "UV_PROJECT_ENVIRONMENT": str(venv),
        "UV_PYTHON": str(venv / "bin" / "python"),
    }
    run([uv, "sync", "--extra", "all", "--locked"], sync_env, checkout)
    if not entry.exists():
        raise RuntimeError("The Hermes install has no hermes-acp entry point")
    return entry


def save_sessions(home: Path, dest: Path) -> None:
    """Copy Hermes's session records into the agent logs, skipping links."""
    for name in SESSION_RECORDS:
        source = home / name
        paths = sorted(source.rglob("*")) if source.is_dir() else [source]
        for path in paths:
            if path.is_symlink() or not path.is_file():
                continue
            target = dest / path.relative_to(home)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)


def main() -> None:
    env = dict(os.environ)
    try:
        model = requested_model(env)
        check_endpoint(env)
    except ValueError as error:
        sys.exit(f"harbor-hermes-acp: {error}")
    root = Path.home() / ".harbor-hermes" / HERMES_COMMIT
    entry = install(root)
    home = root / "home"
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.yaml").write_text(hermes_config(model))
    code = subprocess.run([str(entry)], env=child_env(env, home)).returncode
    if AGENT_LOGS.is_dir():
        save_sessions(home, AGENT_LOGS / "hermes")
    sys.exit(code)
