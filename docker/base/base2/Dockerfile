# Step 1: Start from an official Python base image.
FROM python:3.11-slim

# Step 2: Set a working directory inside the container.
WORKDIR /app

# Step 3: Install common system dependencies like cron.
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    gnupg \
    ca-certificates \
    unzip \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpangocairo-1.0-0 \
    libgtk-3-0 \
    xvfb \
    xserver-xephyr \
    tigervnc-standalone-server \
    xfonts-base \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# 4. Install Google Chrome Stable
RUN wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt-get update \
    && apt-get install -y ./google-chrome-stable_current_amd64.deb \
    && rm google-chrome-stable_current_amd64.deb

# Step 5: Copy the BASE requirements file.
COPY docker/base/core-requirements.txt .
RUN pip install --no-cache-dir -r core-requirements.txt

# Step 6: Install the foundational Python packages.
COPY common/requirements.txt /app/common/requirements.txt
RUN pip install --no-cache-dir -r /app/common/requirements.txt


# Step 7: Copy the shared common code.
COPY common/ /app/common/

