# Step 1: Start from our base image
FROM sentinel/base-image:1.0

# Step 2: Set a working directory inside the container.
WORKDIR /app

# Step 3: Copy the dependencies file first.
COPY microservices/web-scraper/requirements.txt .

# Step 4: Install cron and python packages
RUN apt-get update && apt-get install -y cron && \
    pip install --no-cache-dir -r requirements.txt && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Step 5: Copy the rest of your application's source code.
COPY microservices/web-scraper/ /app/microservices/web-scraper

# Step 6: Define the command to run your application.
CMD ["python", "-m", "microservices.web-scraper.main"]
