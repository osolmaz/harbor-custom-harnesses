"""Attested entry points for the copied Anonbench1 adapters.

The `anonbench1_pi`, `anonbench1_openclaw`, and `anonbench1_hermes` modules are
verbatim copies of the reviewed harbor-config adapters, kept 1-1 by
`scripts/sync_anonbench1_adapters.py`. This module adds exactly one behavior on
top: `setup()` re-verifies the installed agent version against the pin and
fails the trial on any mismatch, so a run cannot silently test a different
build. That is the failure mode of the 2026-10-06 overnight runs, which spent
about USD 246 on harness builds the operator did not ask for.

The Harbor-HF agent presets reference these classes, not the copied ones.
"""

from typing import override

from harbor.environments.base import BaseEnvironment

from anonbench1_adapters.anonbench1_hermes import Anonbench1Hermes as _CopiedHermes
from anonbench1_adapters.anonbench1_openclaw import (
    Anonbench1OpenClaw as _CopiedOpenClaw,
)
from anonbench1_adapters.anonbench1_pi import Anonbench1Pi as _CopiedPi
from anonbench1_adapters.attestation import attest_version


class Anonbench1Pi(_CopiedPi):
    """The copied Pi adapter, plus build attestation in setup."""

    @override
    async def setup(self, environment: BaseEnvironment) -> None:
        await super().setup(environment)
        await attest_version(self, environment, "pi")


class Anonbench1OpenClaw(_CopiedOpenClaw):
    """The copied OpenClaw adapter, plus build attestation in setup."""

    @override
    async def setup(self, environment: BaseEnvironment) -> None:
        await super().setup(environment)
        await attest_version(self, environment, "openclaw")


class Anonbench1Hermes(_CopiedHermes):
    """The copied Hermes adapter, plus build attestation in setup."""

    @override
    async def setup(self, environment: BaseEnvironment) -> None:
        await super().setup(environment)
        await attest_version(self, environment, "hermes")
