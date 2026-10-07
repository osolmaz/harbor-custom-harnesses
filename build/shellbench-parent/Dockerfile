# Derived Harbor-HF parent worker for ShellBench runs: the reviewed parent image
# plus the pinned native ShellBench adapters. The base image is pinned by digest
# and never replaced. Build from the repository root:
#
#   docker buildx build --platform linux/amd64 \
#     -f build/shellbench-parent/Dockerfile --output type=local,dest=dist/shellbench-parent .
#
# The operator points HARBOR_HF_PARENT_IMAGE at the pushed image digest. The
# wheel carries no credentials and no task data.
FROM ghcr.io/huggingface/harbor-hf-trial-worker@sha256:f01b7ce139cd705a752411417fbd5d4783fc9f128b0dd156b32d5f2ee8103417

COPY packages/shellbench-adapters/dist/harbor_shellbench_adapters-0.1.0rc1-py3-none-any.whl /tmp/

RUN uv pip install --python /opt/harbor-hf-parent \
        /tmp/harbor_shellbench_adapters-0.1.0rc1-py3-none-any.whl \
    && python -c "from shellbench_adapters import ShellBenchHermes, ShellBenchOpenClaw, ShellBenchPi" \
    && rm /tmp/harbor_shellbench_adapters-0.1.0rc1-py3-none-any.whl
