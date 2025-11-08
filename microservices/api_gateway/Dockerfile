# Step 1: Start from an official Python base image.
FROM sentinel/base-image:1.0

WORKDIR /app

# install system deps for any compiled packages
RUN apt-get update && apt-get install -y build-essential && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1
ENV API_WORKERS=2
ENV HTTP_TIMEOUT=15

CMD ["sh", "-c", "gunicorn -k uvicorn.workers.UvicornWorker main:app --bind 0.0.0.0:8000 --workers ${API_WORKERS:-2} --timeout 120"]
