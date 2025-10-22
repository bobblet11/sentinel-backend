# Step 1: Start from an official Python base image.
FROM python:3.13-slim

# Step 2: Set a working directory inside the container.
WORKDIR /app

# Step 3: Copy the dependencies file first.
COPY microservices/ingestor/requirements.txt .

# Step 4: Install the Python dependencies.
RUN pip install --no-cache-dir -r requirements.txt

# Step 5: Copy the rest of your application's source code.
COPY common/ /app/common/
COPY microservices/ingestor/ /app/microservices/ingestor

# Step 6: set import path
ENV PYTHONPATH "${PYTHONPATH}:/app"

# Step 7: Set the final working directory to your application's folder.
WORKDIR /app/microservices/ingestor

# Step 8: Define the command to run your application.
CMD ["python", "main.py"]