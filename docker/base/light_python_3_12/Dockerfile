# Step 1: Start from an official Python base image.
FROM python:3.12-bullseye

# Step 2: Set a working directory inside the container.
WORKDIR /app

# Step 3: Install common system dependencies and browser (Chrome for amd64, Chromium for arm64)
RUN apt-get update && apt-get install -y --no-install-recommends \
    cron \
    wget \
    gnupg \
    ca-certificates \
    unzip \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Step 4: Copy the BASE requirements file.
COPY docker/base/core-requirements.txt .

# Step 5: Install the foundational Python packages.
RUN pip install --no-cache-dir -r core-requirements.txt

COPY common/requirements.txt /app/common/requirements.txt
RUN pip install --no-cache-dir -r /app/common/requirements.txt
