# Step 1: Start from our base image
FROM sentinel/base-image:1.1

WORKDIR /app

RUN apt-get update && apt-get install -y cron
RUN apt-get clean && rm -rf /var/lib/apt/lists/*


COPY microservices/web_scraper/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY microservices/web_scraper/ /app/microservices/web_scraper
RUN touch /var/log/service.log

CMD ["python", "-m", "microservices.web_scraper.main", ">>", "/var/log/service.log", "2>&1"]
