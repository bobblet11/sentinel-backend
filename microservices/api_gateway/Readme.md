# Sentinel API Gateway

This is the **API Gateway** for Sentinel.  
It exposes HTTP endpoints, creates analysis jobs, and publishes them to Redis for downstream services to process.

---

## What this service does

- Exposes REST APIs using FastAPI
- Accepts analysis requests (`/analysis/analyze`)
- Creates jobs and tracks job status (in-memory)
- Publishes jobs to Redis Streams for async processing
- Proxies / checks connectivity to other services (DB, NLP, Web Scraper)

---

## Requirements

- Python 3.10+
- Redis running locally or via Docker
- Virtualenv activated (`sentinel-env`)

---

## Environment Variables

```bash
REDIS_HOST=localhost
REDIS_PORT=6379
JOB_STREAM=sentinel.jobs

DB_SERVICE_URL=http://localhost:8001
NLP_URL=http://localhost:8002
WEB_SCRAPER_URL=http://localhost:8003

HTTP_TIMEOUT=15
 
---

## Install Dependencies
'pip install -r requirements.txt'


## Run Locally (Development)
'uvicorn microservices.api_gateway.main:app --reload --port 8000'


## Service will be available at:
'http://localhost:8000'


## Health Check
'curl http://127.0.0.1:8000/health/'
Response -> { "status": "ok" }

---


## Submit Analysis Job
'POST /analysis/analyze'

# Request Body:
{
  "url": "https://example.com",
  "content": "article text here"
}

# Response
{
  "job_id": "uuid",
  "status": "PENDING"
}


## Check Job Status
'GET /analysis/jobs/{job_id}'

# Response will be:

-> If job is pending/running:

{
  "job_id": "uuid",
  "status": "PENDING"
}


-> If job is completed:

{
  "result": { ...analysis result... }
}




