"""Sync the copied ShellBench adapter files 1-1 with their harbor-config source.

The three adapter modules in `packages/shellbench-adapters/src/shellbench_adapters/`
are verbatim copies of the reviewed harbor-config run folder. This script is the
only way they change: it copies the source files byte for byte and reports
drift. Run it after the harbor-config adapters change, commit the result, and
let the CI sync-check step fail any copy that was edited by hand instead.

Usage:

    uv run --project packages/shellbench-adapters \
        python scripts/sync_shellbench_adapters.py [--check]
"""

import argparse
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_ROOT = Path(
    "~/repos/harbor-config/runs/2026-10-05-shellbench-preliminary"
)
PACKAGE = "packages/shellbench-adapters"
TARGET_DIR = "src/shellbench_adapters"

COPIED_FILES = (
    ("pi/adapter/shellbench_pi.py", "shellbench_pi.py"),
    ("openclaw/adapter/shellbench_openclaw.py", "shellbench_openclaw.py"),
    ("hermes/adapter/shellbench_hermes.py", "shellbench_hermes.py"),
)


def sources(args: argparse.Namespace) -> list[tuple[Path, Path]]:
    pairs: list[tuple[Path, Path]] = []
    for source_relative, target_name in COPIED_FILES:
        source = args.source_root.expanduser() / source_relative
        target = REPO_ROOT / PACKAGE / TARGET_DIR / target_name
        pairs.append((source, target))
    return pairs


def sync(pairs: list[tuple[Path, Path]]) -> list[str]:
    changed = []
    for source, target in pairs:
        if not source.is_file():
            raise FileNotFoundError(f"missing source: {source}")
        before = target.read_bytes()
        shutil.copyfile(source, target)
        if target.read_bytes() != before:
            changed.append(f"{target.name} synced from {source}")
    return changed


def check(pairs: list[tuple[Path, Path]]) -> list[str]:
    drifted = []
    for source, target in pairs:
        if target.read_bytes() != source.read_bytes():
            drifted.append(f"{target.name} differs from {source}")
    return drifted


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-root",
        type=Path,
        default=DEFAULT_SOURCE_ROOT,
        help="The harbor-config run folder the copies come from.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail with a nonzero exit when the copies drift from the source.",
    )
    args = parser.parse_args()
    pairs = sources(args)
    if args.check:
        drifted = check(pairs)
        if drifted:
            for line in drifted:
                print(f"drift: {line}", file=sys.stderr)
            print(
                "run scripts/sync_shellbench_adapters.py and commit the result",
                file=sys.stderr,
            )
            return 1
        print("in sync")
        return 0
    for line in sync(pairs):
        print(line)
    print("in sync")
    return 0


if __name__ == "__main__":
    sys.exit(main())
