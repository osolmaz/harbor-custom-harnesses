# ShellBench structured: Qwen3.8 27B with thinking on and off

Measure the cost of provider thinking inside the same reply limit. Both arms run Qwen3.8 27B through Novita with localpi, the continuation guard, and a 16,384-token reply limit on the same 6 ShellBench structured tasks with two attempts each. The arms differ only in `--thinking high` and `--thinking off`.

Reconstructed on 2026-10-05 from the Harbor-HF run records, as described in [the run record spec](../../docs/2026-10-05-benchmark-run-records-spec.md). Results stay in the Harbor-HF run Bucket.

## Arms

| Arm | Model | Pin | Original manifest | Wheel | Main run | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| [`localpi-think`](localpi-think/) | `Qwen/Qwen3.8-27B:novita` | `0e69721cf1` | `harnesses/localpi/harbor-agent-think-localpi.json` | `0.1.0rc7` | `run-96979769e4a4252dd8e5e3b5` | finished, 12 of 12 trials completed, 2 errored |
| [`localpi-nothink`](localpi-nothink/) | `Qwen/Qwen3.8-27B:novita` | `0e69721cf1` | `harnesses/localpi/harbor-agent-nothink-localpi.json` | `0.1.0rc7` | `run-a18e717a998a2fadead350b1` | finished, 12 of 12 trials completed, 1 errored |

## How this record was made

- The first main run started on 2026-09-24 (UTC).
- Each job config is the run's own Harbor job config. Its agent source keeps the pin that ran, which points into `harnesses/` and not into this folder.
- Each harness folder copies the files at that pin: the manifest, saved as `harbor-agent.json`, and `pyproject.toml` and `uv.lock` from `harnesses/`, the adapter source from `src/harbor_pi_code_mode/`, and the payload build inputs from `build/pi-code-mode/`. `build/wheel.json` holds the release wheel and the sha256 that `uv.lock` pins.
- The adapter actually ran from inside that wheel. `src/` is the source at the pin. The wheels were uploaded by hand, so nothing proves that the wheel was built from this source. To run this again, use the original pin.
- The release tag for the rc7 wheel points to an older commit on `main`, not to the commit that built the wheel. The adapter source here comes from the pinned commit, which locks that wheel. It was not compared with the wheel's contents.
