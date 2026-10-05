# Terminal-Bench 2.1: DeepSeek V4.1 Flash with direct Pi and Pi Code Mode

Compare direct Pi with Pi Code Mode on all Terminal-Bench 2.1 tasks, using DeepSeek V4.1 Flash through Novita. Both arms use the same runtime wheel and differ only in `--code-mode direct` and `--code-mode code`.

Reconstructed on 2026-10-05 from the Harbor-HF run records, as described in [the run record spec](../../docs/2026-10-05-benchmark-run-records-spec.md). Results stay in the Harbor-HF run Bucket.

## Arms

| Arm | Model | Pin | Original manifest | Wheel | Main run | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| [`pi-code-mode-direct`](pi-code-mode-direct/) | `deepseek-ai/DeepSeek-V4.1-Flash:novita` | `e2b5a27d57` | `harnesses/pi-code-mode/harbor-agent-direct.json` | `0.1.0rc4` | `run-f8426a62bb0cea4dbba5e2d1` | finished, 89 of 89 trials completed, 9 errored |
| [`pi-code-mode-code`](pi-code-mode-code/) | `deepseek-ai/DeepSeek-V4.1-Flash:novita` | `e2b5a27d57` | `harnesses/pi-code-mode/harbor-agent-code.json` | `0.1.0rc4` | `run-4b9e49566cff51cf698acd86` | finished, 89 of 89 trials completed, 4 errored |

## Other runs with the same pins

| Run | Arm | Kind | Status |
| :--- | :--- | :--- | :--- |
| `run-3c3b5e169eddb252918e61d8` | `pi-code-mode-direct` | earlier launch of the same config | no Harbor job result |
| `run-549db1a196e8dcc4a7dc12e4` | `pi-code-mode-code` | earlier launch of the same config | no Harbor job result |

## Earlier probes

These ran before the main runs, with other pins or manifests. They have no harness folder here.

| Run | Date | Pin | Manifest | Model | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `run-31ca52ec57e0f5280138baea` | 2026-09-11 | `e2b5a27d57` | `harbor-agent-direct-canary.json` | `deepseek-ai/DeepSeek-V4.1-Flash:novita` | finished, 1 of 1 trials completed |
| `run-aa7c6b9ab57d17cfa8f2a0d3` | 2026-09-11 | `e2b5a27d57` | `harbor-agent-code-canary.json` | `deepseek-ai/DeepSeek-V4.1-Flash:novita` | finished, 1 of 1 trials completed |
| `run-8b0949fb8047286537555158` | 2026-09-11 | `e2b5a27d57` | `harbor-agent-code-canary.json` | `deepseek-ai/DeepSeek-V4.1-Flash:novita` | finished, 1 of 1 trials completed |
| `run-05a47aa212dc0b861cfa11bc` | 2026-09-11 | `e2b5a27d57` | `harbor-agent-code-canary.json` | `deepseek-ai/DeepSeek-V4.1-Flash:novita` | finished, 1 of 1 trials completed |
| `run-fa4d8948560163da643369f6` | 2026-09-11 | `e2b5a27d57` | `harbor-agent-code-canary.json` | `deepseek-ai/DeepSeek-V4.1-Flash:novita` | finished, 1 of 1 trials completed |

## How this record was made

- The first main run started on 2026-09-11 (UTC).
- Each job config is the run's own Harbor job config. Its agent source keeps the pin that ran, which points into `harnesses/` and not into this folder.
- Each harness folder copies the files at that pin: the manifest, saved as `harbor-agent.json`, and `pyproject.toml` and `uv.lock` from `harnesses/`, the adapter source from `src/harbor_pi_code_mode/`, and the payload build inputs from `build/pi-code-mode/`. `build/wheel.json` holds the release wheel and the sha256 that `uv.lock` pins.
- The adapter actually ran from inside that wheel. `src/` is the source at the pin. The wheels were uploaded by hand, so nothing proves that the wheel was built from this source. To run this again, use the original pin.
- The adapter source and payload build inputs at the pin are identical to the wheel's release tag.
