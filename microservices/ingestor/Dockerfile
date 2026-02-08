# Step 1: Start from our base image
FROM sentinel/base-image:1.0

# Step 2: Set a working directory inside the container.
WORKDIR /app

# Step 3: Copy the dependencies file first.
COPY microservices/ingestor/requirements.txt .

# Step 4: Install cron and python packages
RUN apt-get update && apt-get install -y cron dos2unix && \
    pip install --no-cache-dir -r requirements.txt && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Step 5: Copy the rest of your application's source code.
COPY microservices/ingestor/ /app/microservices/ingestor
COPY common/ /app/common/

# Step 6: Copy the cronjob file into the container.
COPY microservices/ingestor/cronjob /tmp/app-cronjob

# Step 6: Format and permission
RUN echo "" >> /tmp/app-cronjob
RUN chmod 0644 /tmp/app-cronjob
RUN dos2unix /tmp/app-cronjob
RUN crontab /tmp/app-cronjob
RUN rm /tmp/app-cronjob

# # Step 8: Define the command to run your application.
CMD ["/bin/sh", "-c", "printenv > /etc/environment && cron -f"]
