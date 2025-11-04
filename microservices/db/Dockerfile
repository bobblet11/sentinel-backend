# Step 1: Start from our base image
FROM sentinel/base-image:1.0

# Step 2: Set a working directory inside the container.
WORKDIR /app

# Step 3: Copy the dependencies file first.
COPY microservices/db/requirements.txt .

# Step 4: Install python packages
RUN pip install --no-cache-dir -r requirements.txt

# Step 5: Copy the rest of your application's source code.
COPY microservices/db/ /app/microservices/db

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Expose the service port
EXPOSE 8001

# Run the application
CMD ["python", "-m", "microservices.db.main"]
