# API Service

## What It Does

The API service is the external entry point to the Sentinel backend. It accepts article analysis jobs, exposes job status and result endpoints, and provides read access to stored article intelligence such as topics and outlets.

## Main Responsibilities

- receive article submissions from clients
- create and track processing jobs
- publish work into the Redis Stream pipeline
- return completed results in a client-friendly shape
- expose query endpoints over stored backend data

## Key Design Points

- Built with FastAPI as the HTTP gateway for the platform.
- Acts as the boundary between synchronous client requests and the asynchronous backend pipeline.
- Uses PostgreSQL for durable job and article records.
- Uses Redis-backed result storage to serve completed analyses quickly.
- Avoids redundant work by checking for existing or stale jobs before creating new ones.

## Interfaces

Primary endpoint files live under `app/api/v1/endpoints/`.

Common endpoints include:

- `POST /api/v1/jobs`
- `GET /api/v1/jobs/{job_id}`
- `GET /api/v1/jobs/{job_uid}/result`
- `GET /api/v1/articles`
- `GET /api/v1/topics`
- `GET /api/v1/outlets`

## Important Files

- `app/main.py` for FastAPI startup and middleware setup
- `app/api/v1/api.py` for route registration
- `app/api/v1/endpoints/jobs.py` for job submission and polling flow

