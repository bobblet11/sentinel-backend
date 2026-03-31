FROM sentinel/python-light-common:3.12

WORKDIR /app

# install ingestor dependencies
COPY microservices/ingestor/requirements.txt .
RUN apt-get update && apt-get install -y --no-install-recommends \
    cron dos2unix \
    && pip install --no-cache-dir -r requirements.txt \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# copy code
COPY microservices/ingestor/ /app/microservices/ingestor

# copy the cronjob file into correct place for cron registration
COPY microservices/ingestor/cronjob /tmp/app-cronjob

# format and permission of cron
RUN echo "" >> /tmp/app-cronjob
RUN chmod 0644 /tmp/app-cronjob
RUN dos2unix /tmp/app-cronjob
RUN crontab /tmp/app-cronjob
RUN rm /tmp/app-cronjob

CMD ["/bin/sh", "-c", "printenv > /etc/environment && cron -f"]
