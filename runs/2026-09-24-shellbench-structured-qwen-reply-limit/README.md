# ShellBench structured: plain Pi against the localpi continuation guard

Measure the localpi continuation guard on Qwen3.8 27B through Novita. Both arms use the same 16,384-token reply limit on the same 6 ShellBench structured tasks. One arm starts Pi directly, and the other starts it through localpi with the guard, which continues a reply that the limit cut off up to two times.

Reconstructed on 2026-10-05 from the Harbor-HF run records, as described in [the run record spec](../../docs/2026-10-05-benchmark-run-records-spec.md). Results stay in the Harbor-HF run Bucket.

## Arms

| Arm | Model | Pin | Original manifest | Wheel | Main run | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| [`localpi-plain-pi`](localpi-plain-pi/) | `Qwen/Qwen3.8-27B:novita` | `fbcb9c645d` | `harnesses/localpi/harbor-agent-limit-pi.json` | `0.1.0rc6` | `run-2c51e6a24d8a916d3281b49d` | finished, 6 of 6 trials completed |
| [`localpi-guard`](localpi-guard/) | `Qwen/Qwen3.8-27B:novita` | `fbcb9c645d` | `harnesses/localpi/harbor-agent-limit-localpi.json` | `0.1.0rc6` | `run-1a21d892f07ffce87dda3aab` | finished, 6 of 6 trials completed |

## Earlier probes

These ran before the main runs, with other pins or manifests. They have no harness folder here.

| Run | Date | Pin | Manifest | Model | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `run-b4d964c9cc7da32bd20aa688` | 2026-09-24 | `019f9afcd2` | `harbor-agent-localpi-canary.json` | `Qwen/Qwen3.8-27B:novita` | finished, 1 of 1 trials completed |
| `run-97ac59f5a3f4d0bd77763490` | 2026-09-24 | `019f9afcd2` | `harbor-agent-localpi.json` | `Qwen/Qwen3.8-27B:novita` | finished, 1 of 1 trials completed |
| `run-9d4f3c7a7baa7deb78c14909` | 2026-09-24 | `019f9afcd2` | `harbor-agent-localpi.json` | `Qwen/Qwen3-32B:deepinfra` | finished, 1 of 1 trials completed |

## How this record was made

- The first main run started on 2026-09-24 (UTC).
- Each job config is the run's own Harbor job config. Its agent source keeps the pin that ran, which points into `harnesses/` and not into this folder.
- Each harness folder copies the files at that pin: the manifest, saved as `harbor-agent.json`, and `pyproject.toml` and `uv.lock` from `harnesses/`, the adapter source from `src/harbor_pi_code_mode/`, and the payload build inputs from `build/pi-code-mode/`. `build/wheel.json` holds the release wheel and the sha256 that `uv.lock` pins.
- The adapter actually ran from inside that wheel, so `src/` is a record of the code the wheel was built from. To run this again, use the original pin.
- The release tag for the rc6 wheel points to an older commit on `main`, not to the commit that built the wheel. The adapter source here comes from the pinned commit, which locks that wheel. It was not compared with the wheel's contents.
