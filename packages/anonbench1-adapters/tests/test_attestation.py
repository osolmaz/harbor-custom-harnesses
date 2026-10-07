"""Tests for build attestation. No inference and no task data."""

import json
from pathlib import Path
from typing import override

import pytest
from harbor.agents.installed.base import BaseInstalledAgent

from anonbench1_adapters.attestation import attest_version, record_attestation


class FakeResult:
    def __init__(self, return_code: int = 0, stdout: str = "") -> None:
        self.return_code = return_code
        self.stdout = stdout


class FakeEnvironment:
    def __init__(self, result: FakeResult) -> None:
        self.result = result
        self.commands: list[str] = []

    async def exec(self, command: str, **kwargs: object) -> FakeResult:
        self.commands.append(command)
        return self.result


class FakeAgent(BaseInstalledAgent):
    def __init__(self, tmp_path: Path, version: str | None) -> None:
        super().__init__(logs_dir=tmp_path, model_name="openai/test-model")
        self._version = version

    @staticmethod
    @override
    def name() -> str:
        return "fake"

    @override
    async def install(self, environment) -> None:  # noqa: ANN001 -- test double
        raise AssertionError("not used in attestation tests")

    @override
    async def run(self, instruction, environment, context) -> None:  # noqa: ANN001
        raise AssertionError("not used in attestation tests")

    @override
    def get_version_command(self) -> str | None:
        return "fake --version"


def agent(tmp_path: Path, version: str | None = None) -> FakeAgent:
    return FakeAgent(tmp_path, version)


async def test_attestation_passes_when_the_version_matches_the_pin(
    tmp_path: Path,
) -> None:
    environment = FakeEnvironment(FakeResult(stdout="1.0.4\n"))
    verified = await attest_version(
        agent(tmp_path, "1.0.4"),
        environment,  # ty: ignore[invalid-argument-type]
        "pi",
    )
    assert verified == "1.0.4"
    evidence = json.loads((tmp_path / "attestation.json").read_text())
    assert evidence == {
        "agent": "pi",
        "attested_version": "1.0.4",
        "pinned_version": "1.0.4",
        "command": "fake --version",
    }


async def test_attestation_fails_on_a_different_installed_version(
    tmp_path: Path,
) -> None:
    environment = FakeEnvironment(FakeResult(stdout="2026.9.5\n"))
    with pytest.raises(RuntimeError, match="attested version .* != pinned"):
        await attest_version(
            agent(tmp_path, "2026.9.8"),
            environment,  # ty: ignore[invalid-argument-type]
            "openclaw",
        )
    assert not (tmp_path / "attestation.json").exists()


async def test_attestation_fails_when_the_version_command_fails(tmp_path: Path) -> None:
    environment = FakeEnvironment(FakeResult(return_code=127))
    with pytest.raises(RuntimeError, match="version command exited 127"):
        await attest_version(
            agent(tmp_path, "1.0.4"),
            environment,  # ty: ignore[invalid-argument-type]
            "pi",
        )


async def test_attestation_requires_a_pin(tmp_path: Path) -> None:
    environment = FakeEnvironment(FakeResult(stdout="1.0.4"))
    with pytest.raises(RuntimeError, match="pin the version argument"):
        await attest_version(
            agent(tmp_path, None),
            environment,  # ty: ignore[invalid-argument-type]
            "pi",
        )


def test_record_attestation_writes_sorted_json(tmp_path: Path) -> None:
    record_attestation(
        tmp_path, "hermes", "v2026.9.24", "v2026.9.24", "hermes --version"
    )
    assert json.loads((tmp_path / "attestation.json").read_text()) == {
        "agent": "hermes",
        "attested_version": "v2026.9.24",
        "pinned_version": "v2026.9.24",
        "command": "hermes --version",
    }
