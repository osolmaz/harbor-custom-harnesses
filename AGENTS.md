# Repository instructions

- This repository is the Harbor-HF customization repository: it holds reviewed harness adapters,
  their pinned runtimes, and the integration code those harnesses need.
- Keep harness-specific behavior here, not in the Harbor-HF service.
- No tasks from any benchmark ever enter this repository. No task files, task
  directories, task names or IDs, instructions, environments, rubrics, checks, reference
  solutions, agent trajectories, workspaces, or outputs. Presets may name a benchmark
  preset id and reference a task checkout in another repository by its pinned commit;
  they never inline task content. Everything else holds, even when a task seems public.
- Use native Harbor source manifests, uv lockfiles, ACP, and documented Pi APIs.
- Pin executable dependencies and verify runtime payloads before publication.
- Never publish credentials, operator deployment values, private run records, or local paths.
- Benchmark run records under `runs/` follow `docs/2026-10-05-benchmark-run-records-spec.md`.
  They hold no credential, private model name, private endpoint, or local path.
- Do not run real model inference locally. Tests use fake protocol peers.
- Before paid remote work, verify task authorization, cost bounds, durable outputs, and cleanup.
- Use Python 3.12+, uv, Ruff, ty, pytest, and the configured Slophammer checks.
- Keep unit test coverage at or above 85%.
- Use Conventional Commits. Do not add coding-agent branding to commits.
- Do not merge a service integration until its explicitly authorized remote canary passes.
