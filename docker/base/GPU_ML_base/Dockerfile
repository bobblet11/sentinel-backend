FROM nvidia/cuda:12.1.1-cudnn8-devel-ubuntu22.04

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=100

# Install Python 3.12 + pip
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.12 python3.12-venv python3.12-dev python3-pip \
    build-essential curl gnupg ca-certificates unzip \
    && ln -s /usr/bin/python3.12 /usr/bin/python \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# CUDA PyTorch (2.5GB+)
RUN pip install --no-cache-dir \
    torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# Copy/install common + NLP deps (same as CPU base)
WORKDIR /app
COPY docker/base/core-requirements.txt  .
COPY common/requirements.txt .
COPY docker/base/core-nlp-requirements.txt  .

RUN pip install --no-cache-dir \
    -r core-requirements.txt \
    -r requirements.txt \
    -r core-nlp-requirements.txt \
    && rm -rf core-requirements.txt requirements.txt core-nlp-requirements.txt

COPY common/ /app/common/
