"""Pinned native Harbor adapters for the ShellBench benchmark runs.

The adapters are copied from the reviewed harbor-config run folder
`runs/2026-10-05-shellbench-preliminary` and build on Harbor at the pinned
upstream commit 3c823808, the revision the Harbor-HF launch contract checks.
Each adapter attests the installed agent version at setup time; see
`attestation.py`.
"""

from shellbench_adapters.shellbench_hermes import ShellBenchHermes
from shellbench_adapters.shellbench_openclaw import ShellBenchOpenClaw
from shellbench_adapters.shellbench_pi import ShellBenchPi

__all__ = ["ShellBenchHermes", "ShellBenchOpenClaw", "ShellBenchPi"]
