---
title: ShellBench native adapters on Harbor-HF
author: Onur Solmaz <2453968+osolmaz@users.noreply.github.com>
date: 2026-10-07
tags: [harbor-hf, shellbench, harness, attestation]
---

# ShellBench native adapters on Harbor-HF

The 2026-10-06 overnight runs used the wrong harness builds (about USD 246 spent; see the
notes repository, `2026-10-07-shellbench-harbor-hf-wrong-harness-runs.md`). This document
is the correction mechanism: the reviewed harbor-config adapters, unmodified in behavior,
running as native Harbor agents on Harbor-HF, with a build attestation that fails a trial
whose installed agent does not match the pin.

## Why native, not another ACP harness

The harbor-config adapters are native Harbor installed-agent subclasses. They carry the
reviewed behavior: pinned installers, the required OpenClaw `runtime` option, custom
endpoint registration, Hermes usage scraping from `state.db`, and install retries. An ACP
rewrite would be a second implementation of the same behavior, which is how the wrong
build happened in the first place. The adapters run as themselves, through Harbor's
`import_path` agent loading.

Harbor-HF's launch contract pins Harbor to
`harbor-framework/harbor@3c82380859d187957cfd5cd64802b076d9779550` and refuses to launch
anything else (`harbor_hf_agents.launch.check_revision`). The osolmaz Harbor fork that
harbor-config pins is 84 commits ahead and cannot be used here. The ported adapters are
therefore validated against the upstream pin: every Harbor API they use
(`_build_custom_models_json`, `_build_full_openclaw_config`, `get_version_command`,
`_build_config_yaml`, `with_prompt_template`, the install retry hooks) exists at that
commit, and the package tests run against exactly that revision.

## Mechanism

1. **Adapter wheel.** `packages/shellbench-adapters` builds the pure-Python wheel
   `harbor_shellbench_adapters`. It declares no runtime dependencies: Harbor comes from
   the parent image, so installing the wheel can never move the Harbor revision the launch
   contract checks. The dev group pins the same upstream commit for the tests.
2. **Derived parent image.** `build/shellbench-parent/Dockerfile` starts from the reviewed
   parent image at its exact digest, installs the pinned wheel into
   `/opt/harbor-hf-parent`, verifies the three adapter classes import, and stops. The
   operator builds it for `linux/amd64`, pushes it, and points
   `HARBOR_HF_PARENT_IMAGE` at the resulting digest. The verifier grants
   (`HARBOR_HF_VERIFIER_GRANTS`) pin the same image, so the judge credential continues to
   resolve; both variables change together.
3. **Agent presets.** The `osolmaz/shellbench` preset source gains three `agent-preset-v1`
   files that name the adapter classes by `import_path` and carry the pinned versions and
   model options the harbor-config job configs used:
   - `shellbench-pi-1.0.4.json` → `shellbench_adapters.shellbench_pi:ShellBenchPi`
   - `shellbench-openclaw-2026.9.8.json` → `shellbench_adapters.shellbench_openclaw:ShellBenchOpenClaw`
   - `shellbench-hermes-2026.9.24.json` → `shellbench_adapters.shellbench_hermes:ShellBenchHermes`

   The presets do not embed prices; cost is computed from the run submission's pricing
   block, so one price record per route stays in the submission, where the operator can
   check it.
4. **Build attestation.** `shellbench_adapters.attestation` runs the agent's version
   command as a real request during `setup()`, compares the parsed version with the pin,
   writes `attestation.json` into the agent logs, and fails the trial on any mismatch or
   missing pin. Harbor's native version detection is best-effort and does not compare;
   this is the control that makes the wrong-build failure mode impossible to repeat
   silently.

## What replaced what

The Hermes ACP harness from PR #11 (`harnesses/hermes-acp`) is superseded by the ported
`ShellBenchHermes` adapter. Its branch stays open for reference only: it explains what the
2026-10-06 Hermes run actually executed. The `openclaw-native` ACP harness (OpenClaw
2026.9.5) stays in the repository for its own past runs but is not part of the ShellBench
path; the ShellBench presets stop referencing it.

## Smoke before spend

One task (`003fed-walnut-frame-apology`), one trial per harness, on the
`shellbench-one-task-1-trial` benchmark preset with DeepSeek V4.1 Flash, before any full
run. A smoke passes only when the trial result records the attested version (`pi` 1.0.4,
OpenClaw `2026.9.8`, Hermes `v2026.9.24`), the `attestation.json` artifact is present, and
the trial completes with a nonzero reward path or an explainable failure. Nothing beyond
the smoke starts without the operator's budget approval.
