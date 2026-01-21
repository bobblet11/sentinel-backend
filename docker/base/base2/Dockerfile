# Step 1: Start from an official Python base image.
FROM python:3.11-bullseye

# Step 2: Set a working directory inside the container.
WORKDIR /app

# Step 3: Install common system dependencies and browser (Chrome for amd64, Chromium for arm64)
ARG TARGETARCH
RUN apt-get update && apt-get install -y --no-install-recommends \
    cron \
    wget \
    gnupg \
    ca-certificates \
    unzip \
    && if [ "$TARGETARCH" = "arm64" ]; then \
        # ARM: Install Chromium from apt
        apt-get install -y chromium; \
    else \
        # x86_64: Install Google Chrome
        apt-get install -y \
            libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
            libxkbcommon0 libxcomposite1 libxdamage1 libxext6 libxfixes3 \
            libxrandr2 libgbm1 libasound2 libpangocairo-1.0-0 libgtk-3-0 \
            xvfb xserver-xephyr tigervnc-standalone-server xfonts-base \
        && wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
        && apt-get install -y ./google-chrome-stable_current_amd64.deb \
        && rm google-chrome-stable_current_amd64.deb; \
    fi \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Step 4: Copy the BASE requirements file.
COPY docker/base/core-requirements.txt .

# Step 5: Install the foundational Python packages.
RUN pip install --no-cache-dir -r core-requirements.txt

# Step 6: Install the foundational Python packages.
COPY common/requirements.txt /app/common/requirements.txt
RUN pip install --no-cache-dir -r /app/common/requirements.txt

# Step 7: Copy the shared common code.
COPY common/ /app/common/

