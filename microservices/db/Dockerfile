FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY microservices/db/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY microservices/db/ /app/

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Expose the service port
EXPOSE 8001

# Run the application
CMD ["python", "main.py"]
