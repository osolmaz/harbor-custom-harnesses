"""Attested entry points for the copied ShellBench adapters.

The `shellbench_pi`, `shellbench_openclaw`, and `shellbench_hermes` modules are
verbatim copies of the reviewed harbor-config adapters, kept 1-1 by
`scripts/sync_shellbench_adapters.py`. This module adds exactly one behavior on
top: `setup()` re-verifies the installed agent version against the pin and
fails the trial on any mismatch, so a run cannot silently test a different
build. That is the failure mode of the 2026-10-06 overnight runs, which spent
about USD 246 on harness builds the operator did not ask for.

The Harbor-HF agent presets reference these classes, not the copied ones.
"""

from typing import override

from harbor.environments.base import BaseEnvironment

from shellbench_adapters.attestation import attest_version
from shellbench_adapters.shellbench_hermes import ShellBenchHermes as _CopiedHermes
from shellbench_adapters.shellbench_openclaw import (
    ShellBenchOpenClaw as _CopiedOpenClaw,
)
from shellbench_adapters.shellbench_pi import ShellBenchPi as _CopiedPi


class ShellBenchPi(_CopiedPi):
    """The copied Pi adapter, plus build attestation in setup."""

    @override
    async def setup(self, environment: BaseEnvironment) -> None:
        await super().setup(environment)
        await attest_version(self, environment, "pi")


class ShellBenchOpenClaw(_CopiedOpenClaw):
    """The copied OpenClaw adapter, plus build attestation in setup."""

    @override
    async def setup(self, environment: BaseEnvironment) -> None:
        await super().setup(environment)
        await attest_version(self, environment, "openclaw")


class ShellBenchHermes(_CopiedHermes):
    """The copied Hermes adapter, plus build attestation in setup."""

    @override
    async def setup(self, environment: BaseEnvironment) -> None:
        await super().setup(environment)
        await attest_version(self, environment, "hermes")
