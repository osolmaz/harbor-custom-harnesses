"""Pinned native Harbor adapters for the ShellBench benchmark runs.

The `shellbench_pi`, `shellbench_openclaw`, and `shellbench_hermes` modules are
verbatim copies of the reviewed harbor-config adapters at
`runs/2026-10-05-shellbench-preliminary`, kept 1-1 by
`scripts/sync_shellbench_adapters.py`. They build on Harbor at the pinned
upstream commit 3c823808, the revision the Harbor-HF launch contract checks.

The Harbor-HF agent presets use the attested wrappers from
`shellbench_adapters.attested`, which add build attestation and nothing else.
"""

from shellbench_adapters.attested import (
    ShellBenchHermes,
    ShellBenchOpenClaw,
    ShellBenchPi,
)

__all__ = ["ShellBenchHermes", "ShellBenchOpenClaw", "ShellBenchPi"]
