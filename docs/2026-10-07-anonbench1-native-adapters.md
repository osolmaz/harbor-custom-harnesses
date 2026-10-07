---
title: Anonbench1 native adapters on Harbor-HF
author: Onur Solmaz <2453968+osolmaz@users.noreply.github.com>
date: 2026-10-07
tags: [harbor-hf, anonbench1, harness, attestation]
---

# Anonbench1 native adapters on Harbor-HF

The 2026-10-06 overnight runs used the wrong harness builds (about USD 246 spent; see the
incident note in the private notes repository). This document is the correction
mechanism: the reviewed adapter source, unmodified in behavior, running as native Harbor
agents on Harbor-HF, with a build attestation that fails a trial whose installed agent
does not match the pin.

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

1. **Adapter wheel.** `packages/anonbench1-adapters` builds the pure-Python wheel
   `harbor_anonbench1_adapters`. It declares no runtime dependencies: Harbor comes from
   the parent image, so installing the wheel can never move the Harbor revision the launch
   contract checks. The dev group pins the same upstream commit for the tests. The three
   adapter modules are verbatim copies of the harbor-config run folder, kept 1-1 by
   `scripts/sync_anonbench1_adapters.py`; CI fails on drift. The only added code is the
   `attested.py` wrapper module, which overrides `setup()` to attest the build, and the
   attestation helper itself.
2. **Derived parent image.** `build/anonbench1-parent/Dockerfile` starts from the reviewed
   parent image at its exact digest, installs the pinned wheel into
   `/opt/harbor-hf-parent`, verifies the three adapter classes import, and stops. The
   operator builds it for `linux/amd64`, pushes it as
   `ghcr.io/osolmaz/harbor-hf-customization/anonbench1-parent:<version>` — the same
   namespace and hidden name as the base image — and points `HARBOR_HF_PARENT_IMAGE` at
   the resulting digest. The verifier grants (`HARBOR_HF_VERIFIER_GRANTS`) pin the same
   image, so the judge credential continues to resolve; both variables change together.
3. **Agent presets.** The `osolmaz/anonbench1` preset source gains three `agent-preset-v1`
   files that name the adapter classes by `import_path` and carry the pinned versions and
   model options the harbor-config job configs used:
   - `anonbench1-pi-1.0.4.json` → `anonbench1_adapters.anonbench1_pi:Anonbench1Pi`
   - `anonbench1-openclaw-2026.9.8.json` → `anonbench1_adapters.anonbench1_openclaw:Anonbench1OpenClaw`
   - `anonbench1-hermes-2026.9.24.json` → `anonbench1_adapters.anonbench1_hermes:Anonbench1Hermes`

   The presets do not embed prices; cost is computed from the run submission's pricing
   block, so one price record per route stays in the submission, where the operator can
   check it.
4. **Build attestation.** The `attested.py` wrappers call
   `anonbench1_adapters.attestation` during `setup()`: it runs the agent's version
   command as a real request, compares the parsed version with the pin, writes
   `attestation.json` into the agent logs, and fails the trial on any mismatch or
   missing pin. Harbor's native version detection is best-effort and does not compare;
   this is the control that makes the wrong-build failure mode impossible to repeat
   silently.

## What replaced what

The Hermes ACP harness from PR #11 (`harnesses/hermes-acp`) is superseded by the ported
`Anonbench1Hermes` adapter. Its branch stays open for reference only: it explains what the
2026-10-06 Hermes run actually executed. The `openclaw-native` ACP harness (OpenClaw
2026.9.5) stays in the repository for its own past runs but is not part of the Anonbench1
path; the Anonbench1 presets stop referencing it.

## Naming

Public artifacts carry the hidden `anonbench1` name, never the benchmark name: the base
image, this wheel release (`anonbench1-adapters-*`), and the derived parent image. The
Python package and preset ids inside private repositories keep their descriptive names.

## Smoke before spend

One task, one trial per harness, through the `anonbench1-one-task-1-trial` benchmark
preset with DeepSeek V4.1 Flash, before any full run. The preset names the task; no task
content belongs in this repository. A smoke passes only when the trial result records the attested version (`pi` 1.0.4,
OpenClaw `2026.9.8`, Hermes `v2026.9.24`), the `attestation.json` artifact is present, and
the trial completes with a nonzero reward path or an explainable failure. Nothing beyond
the smoke starts without the operator's budget approval.
