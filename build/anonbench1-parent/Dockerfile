# Derived Harbor-HF parent worker for Anonbench1 runs: the reviewed parent image
# plus the pinned native Anonbench1 adapters. The base image is pinned by digest
# and never replaced. Build from the repository root:
#
#   docker buildx build --platform linux/amd64 \
#     -f build/anonbench1-parent/Dockerfile --output type=local,dest=dist/anonbench1-parent .
#
# The operator points HARBOR_HF_PARENT_IMAGE at the pushed image digest. The
# wheel carries no credentials and no task data.
FROM ghcr.io/huggingface/harbor-hf-trial-worker@sha256:f01b7ce139cd705a752411417fbd5d4783fc9f128b0dd156b32d5f2ee8103417

COPY packages/anonbench1-adapters/dist/harbor_anonbench1_adapters-0.1.0rc1-py3-none-any.whl /tmp/

RUN uv pip install --python /opt/harbor-hf-parent \
        /tmp/harbor_anonbench1_adapters-0.1.0rc1-py3-none-any.whl \
    && python -c "from anonbench1_adapters import Anonbench1Hermes, Anonbench1OpenClaw, Anonbench1Pi" \
    && rm /tmp/harbor_anonbench1_adapters-0.1.0rc1-py3-none-any.whl
