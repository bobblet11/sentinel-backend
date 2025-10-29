# Step 1: Start from an official Python base image.
FROM python:3.12-slim

# Step 2: Set a working directory inside the container.
WORKDIR /app

# Step 3: Install common system dependencies like cron.
RUN apt-get update && apt-get install -y --no-install-recommends \
    cron \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Step 4: Copy the BASE requirements file.
COPY docker/base/core-requirements.txt .

# Step 5: Install the foundational Python packages.
RUN pip install --no-cache-dir -r core-requirements.txt

# Step 6: Copy the shared common code.
COPY common/ /app/common/
