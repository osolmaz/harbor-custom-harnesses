FROM python:3.14-slim@sha256:f85c5697265c178cc6887276c55fe16cf3d14ca35c3df6a5eab3b360534a55d2

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        coreutils \
        curl \
        file \
        findutils \
        git \
        jq \
        less \
        nodejs \
        npm \
        poppler-utils \
        ripgrep \
        tesseract-ocr \
        tesseract-ocr-eng \
        unzip \
        zip \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    httpx==0.28.1 \
    openpyxl==3.1.5 \
    pandas==3.0.6 \
    pdfplumber==0.11.10 \
    pypdf==6.19.0 \
    pytest==8.4.1 \
    pytest-json-ctrf==0.3.5 \
    python-docx==1.2.0 \
    python-pptx==1.0.2 \
    pyyaml==6.0.3 \
    reportlab==5.0.1 \
    requests==2.34.2

# Browser automation for tasks that drive a web page: Playwright with its Chromium build and
# system libraries. NODE_PATH lets task code require("playwright") without a local install.
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
ENV NODE_PATH=/usr/local/lib/node_modules
RUN npm install -g playwright@1.63.0 \
    && playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/* /root/.npm
