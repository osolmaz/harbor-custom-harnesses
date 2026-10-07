"""Build attestation for the ShellBench adapters.

The 2026-10-06 overnight runs spent about USD 246 on harness builds the
operator did not ask for, and the reports did not say so. This module is the
control that would have caught that: after Harbor's best-effort version
detection, the adapter re-runs the version command as a real request, compares
the parsed version with the pinned one, and writes the evidence into the agent
logs. A wrong or missing attestation fails the trial, so a run cannot silently
test a different build.
"""

import json
from pathlib import Path
from typing import Any

from harbor.agents.installed.base import BaseInstalledAgent
from harbor.environments.base import BaseEnvironment


async def attest_version(
    agent: BaseInstalledAgent,
    environment: BaseEnvironment,
    name: str,
) -> str:
    """Re-verify the installed agent version against the pin; fail on any mismatch."""
    command = agent.get_version_command()
    if not command:
        raise RuntimeError(f"{name}: build attestation failed; no version command")
    result: Any = await environment.exec(command=command)
    if result.return_code != 0 or not result.stdout:
        raise RuntimeError(
            f"{name}: build attestation failed; "
            f"version command exited {result.return_code}"
        )
    version = agent.parse_version(result.stdout)
    # The base class owns this attribute; read it for the pin comparison.
    pinned = agent._version  # noqa: SLF001
    if not pinned:
        raise RuntimeError(
            f"{name}: build attestation failed; pin the version argument"
        )
    if version != pinned:
        raise RuntimeError(
            f"{name}: build attestation failed; "
            f"attested version {version!r} != pinned {pinned!r}"
        )
    record_attestation(agent.logs_dir, name, version, pinned, command)
    return version


def record_attestation(
    logs_dir: Path, name: str, version: str, pinned: str, command: str
) -> None:
    """Write the attestation evidence into the agent logs next to the trajectory."""
    record = {
        "agent": name,
        "attested_version": version,
        "pinned_version": pinned,
        "command": command,
    }
    (Path(logs_dir) / "attestation.json").write_text(json.dumps(record, sort_keys=True))
