# Step 1: Start from our base image
FROM sentinel/base-image:1.0

WORKDIR /app

RUN apt-get update && apt-get install -y cron
RUN apt-get clean && rm -rf /var/lib/apt/lists/*


COPY microservices/message_fixer/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY microservices/message_fixer/ /app/microservices/message_fixer
COPY common/ /app/common/

CMD ["python", "-m", "microservices.message_fixer.main"]
