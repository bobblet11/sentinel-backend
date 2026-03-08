FROM python:3.11-bullseye

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=100

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl gnupg ca-certificates unzip \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

COPY docker/base/core-requirements.txt .

RUN pip install --no-cache-dir -r core-requirements.txt \
    && rm -rf core-requirements.txt

