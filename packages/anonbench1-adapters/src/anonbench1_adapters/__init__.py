"""Pinned native Harbor adapters for the Anonbench1 benchmark runs.

The `anonbench1_pi`, `anonbench1_openclaw`, and `anonbench1_hermes` modules are
verbatim copies of the reviewed harbor-config adapters at
`runs/2026-10-05-anonbench1-preliminary`, kept 1-1 by
`scripts/sync_anonbench1_adapters.py`. They build on Harbor at the pinned
upstream commit 3c823808, the revision the Harbor-HF launch contract checks.

The Harbor-HF agent presets use the attested wrappers from
`anonbench1_adapters.attested`, which add build attestation and nothing else.
"""

from anonbench1_adapters.attested import (
    Anonbench1Hermes,
    Anonbench1OpenClaw,
    Anonbench1Pi,
)

__all__ = ["Anonbench1Hermes", "Anonbench1OpenClaw", "Anonbench1Pi"]
