# Step 1: Start from an official Python base image.
FROM sentinel/base-image:1.0

# Step 2: Set a working directory inside the container.
WORKDIR /app

# Step 3: Copy the dependencies file first.
COPY microservices/ingestor/requirements.txt .

# Step 4: Install cron and python packages
RUN apt-get update && apt-get install -y cron && \
    pip install --no-cache-dir -r requirements.txt && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Step 5: Copy the rest of your application's source code.
COPY common/ /app/common/
COPY microservices/ingestor/ /app/microservices/ingestor

# Step 6: Copy the cronjob file into the container.
COPY microservices/ingestor/cronjob /tmp/app-cronjob

# Step 7: Give correct permissions and create log file.
RUN sed -i 's/\r$//' /tmp/app-cronjob && \
    crontab /tmp/app-cronjob && \
    rm /tmp/app-cronjob && \
    touch /var/log/cron.log

# Step 8: Define the command to run your application.
CMD ["cron", "-f"]
