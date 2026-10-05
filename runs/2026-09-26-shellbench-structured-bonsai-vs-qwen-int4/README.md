# ShellBench structured: Ternary Bonsai 2 27B against Qwen3.8 27B INT4

Compare Ternary Bonsai 2 27B, served by llama.cpp, with RedHatAI Qwen3.8 27B INT4, served by vLLM, on all 89 ShellBench structured tasks with one trial each. Both arms run direct Pi through localpi with the same reply limit, thinking-phase output cap, and continuation guard. Apart from the model, the harness flags differ only in the endpoint engine, its context window, and the thinking format that the model needs. The job configs also differ in trial concurrency: 1 for Bonsai and 4 for Qwen.

Reconstructed on 2026-10-05 from the Harbor-HF run records, as described in [the run record spec](../../docs/2026-10-05-benchmark-run-records-spec.md). Results stay in the Harbor-HF run Bucket.

## Arms

| Arm | Model | Pin | Original manifest | Wheel | Main run | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| [`localpi-bonsai`](localpi-bonsai/) | `bonsai-2-27b-ternary` | `9e7fd5255a` | `harnesses/localpi/harbor-agent-llama-cpp-endpoint-cap-canary.json` | `0.1.0rc10` | `run-491655a84aa51063d9f7c519` | finished, 89 of 89 trials completed, 1 errored |
| [`localpi-qwen`](localpi-qwen/) | `RedHatAI/Qwen3.8-27B-INT4` | `9e7fd5255a` | `harnesses/localpi/harbor-agent-qwen-endpoint-cap-canary.json` | `0.1.0rc10` | `run-30ac1880e04a46c6c8880cd9` | finished, 89 of 89 trials completed |

## Other runs with the same pins

| Run | Arm | Kind | Status |
| :--- | :--- | :--- | :--- |
| `run-570bd65298b34028926678ce` | `localpi-bonsai` | compaction canary, 1 task | finished, 1 of 1 trials completed |
| `run-1b7013519f2b38bd27213e4b` | `localpi-qwen` | paired probe, 20 tasks | finished, 20 of 20 trials completed |

## Earlier probes

These ran before the main runs, with other pins or manifests. They have no harness folder here.

| Run | Date | Pin | Manifest | Model | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `run-7bd0d291f566f5a1caf46657` | 2026-09-25 | `8df57c1ecf` | `harbor-agent-qwen-endpoint-cap-canary.json` | `RedHatAI/Qwen3.8-27B-INT4` | finished, 1 of 1 trials completed |
| `run-e4fef7cfc42ae7c2754e45fe` | 2026-09-25 | `063c3f13a1` | `harbor-agent-llama-cpp-endpoint-cap-canary.json` | `bonsai-2-27b-ternary` | finished, 1 of 1 trials completed |
| `run-6d3e1e180264897120b3adc9` | 2026-09-25 | `98334b52a7` | `harbor-agent-llama-cpp-endpoint-cap-canary.json` | `bonsai-2-27b-ternary` | finished, 1 of 1 trials completed |
| `run-c675f025cb89a9969cb9a156` | 2026-09-26 | `98334b52a7` | `harbor-agent-qwen-endpoint-cap-canary.json` | `RedHatAI/Qwen3.8-27B-INT4` | finished, 5 of 5 trials completed |
| `run-cf6d3bdc7d441e596bcebe7b` | 2026-09-26 | `98334b52a7` | `harbor-agent-llama-cpp-endpoint-cap-canary.json` | `bonsai-2-27b-ternary` | not finished, 3 of 5 trials completed, 1 errored |

## How this record was made

- The first main run started on 2026-09-26 (UTC).
- Each job config is the run's own Harbor job config. Its agent source keeps the pin that ran, which points into `harnesses/` and not into this folder.
- Each harness folder copies the files at that pin: the manifest, saved as `harbor-agent.json`, and `pyproject.toml` and `uv.lock` from `harnesses/`, the adapter source from `src/harbor_pi_code_mode/`, and the payload build inputs from `build/pi-code-mode/`. `build/wheel.json` holds the release wheel and the sha256 that `uv.lock` pins.
- The adapter actually ran from inside that wheel. `src/` is the source at the pin. The wheels were uploaded by hand, so nothing proves that the wheel was built from this source. To run this again, use the original pin.
- The adapter source and payload build inputs at the pin are identical to the wheel's release tag.
