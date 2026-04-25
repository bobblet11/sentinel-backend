# API Gateway Microservice

## 1. Methodology

### 1.1 Overview and Architectural Role

The API Gateway microservice serves as the sole external-facing entry point to the Sentinel misinformation detection pipeline. Built on **FastAPI** (Python 3.11), it accepts article submission requests from browser extension clients, coordinates persistence via **PostgreSQL** (SQLAlchemy synchronous ORM), and routes work onto **Redis Streams** for downstream asynchronous processing. The gateway is intentionally stateless with respect to pipeline execution: it enqueues work and exposes polling endpoints, delegating all computational stages to specialised downstream services.

The service is registered under the module `microservices.api.app.main` and exposed on a configurable port (`API_SERVICE_PORT`). The FastAPI application instance is created at module level, enabling Uvicorn to serve it directly.

---

### 1.2 RESTful API Design

The public API surface is minimal and deliberate, consisting of three endpoints registered under the `/api/v1/jobs` prefix:

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/v1/jobs` | Submit a new analysis job |
| `GET` | `/api/v1/jobs/{job_id}` | Poll job status by integer ID |
| `GET` | `/api/v1/jobs/{job_uid}/result` | Retrieve the formatted analysis result by UUID |

The separation of status polling (`/{job_id}`) from result retrieval (`/{job_uid}/result`) reflects a deliberate design choice: status queries are lightweight synchronous reads from the database, while result retrieval involves a time-bounded polling loop against a Redis hash store. Both integer `id` (auto-increment primary key) and `uid` (UUID) are exposed to clients, with `id` used for status tracking and `uid` used as the Redis key for completed results. No article listing or pagination endpoints are exposed; the API is strictly job-centric.

To avoid HTTP 307 redirect overhead from trailing slashes, both `/jobs` and `/jobs/` are registered for the `POST` route. An additional HTTP middleware normalises trailing slashes on all other paths.

---

### 1.3 Request and Response Schemas

Request and response schemas are defined as **Pydantic v2** `BaseModel` classes in `microservices/api/app/dtos/job.py`.

`JobCreate` captures the article URL (mandatory) alongside optional pre-fetched content fields — `article_html`, `article_text`, `article_title`, `article_published_at`, and `article_summary` — permitting the browser extension to supply already-scraped content and thereby bypass the web scraper stage entirely. A boolean `is_background` flag routes the job to either the user-priority or background-priority stream.

`JobResponse` is the standard submission acknowledgement, returning the integer `id`, UUID `uid`, `status` string, `type` string, and ISO-format `created_at` timestamp. Status values are governed by the `JobStatus` `StrEnum`: `pending`, `complete`, and `failed`.

The result endpoint returns an untyped `dict` (`response_model=dict`) whose structure is defined by the `_transform_retrieval_to_frontend_format()` transformation function, producing a JSON document containing `article`, `trustScore`, `biasAnalysis`, `keyClaims`, and `relatedArticles` fields.

---

### 1.4 Database Session Management

Database connectivity follows the **dependency injection** pattern provided by FastAPI. The generator function `get_db()` in `microservices/api/app/db/session.py` yields a `SessionLocal` instance and guarantees closure in a `finally` block, ensuring connections are returned to the pool regardless of request outcome. The SQLAlchemy engine is constructed from environment variables loaded via the shared `common/env/get_env_var.py` utility, which enforces type casting and raises fatal errors on missing configuration.

The session factory is configured with `autocommit=False` and `autoflush=False`, requiring explicit `db.commit()` calls. This is significant in the job submission path: the `create_article` and `create_job` CRUD operations both call `db.flush()` followed by `db.refresh()` to obtain database-generated primary keys within the same transaction, but the transaction is not committed until `publish_job()` has successfully dispatched the message to Redis. This ordering ensures that a Redis message is never published for a job that was not durably persisted.

---

### 1.5 Duplicate Detection Algorithm

The `submit_job` endpoint implements a three-branch duplicate detection algorithm to prevent redundant pipeline executions for articles that have already been submitted or analysed:

1. **Cache hit (completed, result available):** The endpoint queries the `article` table by URL via `get_article_by_url()`. If a matching article is found, `get_latest_job_for_article()` retrieves the most recent job for that article scoped to the same job type. If the job status is `COMPLETE` and the corresponding entry exists in the Redis hash store (`result_hash_store.exists(uid)`), the existing `Job` ORM object is returned immediately as a `JobResponse` without creating any new database records or Redis messages. This path provides instant deduplication for repeat queries.

2. **In-flight job (pending, not stale):** If the latest job is in the `PENDING` state and was created within the last 15 minutes (governed by the `STALE_JOB_THRESHOLD_MINUTES = 15` constant), the same job is returned. The staleness check (`_is_job_stale()`) guards against indefinitely blocking new submissions for jobs that have silently failed. The function normalises timezone-naive `datetime` objects to UTC before comparison.

3. **New submission (no article, or stale/failed job):** If neither of the above conditions is satisfied, the endpoint proceeds to create a new `Article` record, a new `Job` record, publish to Redis, and commit the transaction.

This branching logic is implemented entirely in the synchronous `submit_job` endpoint using explicit conditional checks rather than database-level locking, which introduces a narrow race window under concurrent submission of the same URL.

---

### 1.6 Priority Stream Routing

Message dispatch is handled by `publish_job()` in `microservices/api/app/services/redis_queue.py`. A `RedisPublisherRouter` instance is constructed at module initialisation time with a routing map that associates `JobType.USER` with the `OUTPUT_STREAM` environment variable (typically `user:to.be.scraped`) and `JobType.BACKGROUND` with `background:to.be.scraped`. The router inspects the `header.type` field of each `Message` to select the appropriate Redis stream via `XADD`.

The fast-path optimisation — publishing directly to `user:to.be.retrieval` with `retrieve_from_db=True` and an `article_db_id` set — enables the system to skip the web scraper and NLP stages entirely for articles whose embeddings and claim analysis are already present in the database. This path is engaged when a completed job exists but the Redis hash result has expired, necessitating a re-retrieval without re-processing.

The `Message` schema follows the shared contract defined in `common/models/api/redis_models.py`, comprising a `MessageHeader` (job identity and status), `MessagePayload` (article content fields), and a `stage_timestamps` list for pipeline latency tracking. A timestamp entry for the `INGESTED` stage is appended by `add_timestamp_to_message()` before dispatch.

---

### 1.7 Result Retrieval and Response Transformation

The `get_retrieval_result` endpoint is declared `async` and implements a **long-poll** pattern. Upon invocation, it enters a loop that queries the Redis hash store at one-second intervals, exiting either when a result is found or when the configurable `timeout` query parameter (default 30 seconds, range 5–60) elapses. The use of `asyncio.sleep(1)` yields the event loop between polls, preventing the endpoint from blocking other concurrent requests.

Upon result discovery, `_transform_retrieval_to_frontend_format()` translates the raw retrieval service output into the frontend-expected schema. The transformation performs several operations:

- Extracts article metadata from the `Article` ORM object and truncates `text` to 1,800 characters for the `content` field.
- Iterates over the `matches` list produced by the retrieval layer, constructing `keyClaims` entries with up to three evidence items each. Evidence items encode claim text, source URL, and a binary `stance` classification (`"supporting"` for non-contradicting relations, `"disputing"` for `contradict`).
- Computes the `trustScore` as the integer mean of per-claim `confidence` values; returns zero when no claims are present.
- Delegates bias metadata construction to `_build_bias_analysis()`, which maps the NLP service's `bias_profile` dictionary onto the frontend's `overallBias`, `biasScore`, `confidence`, and `sentiment` fields. Confidence values are normalised from the [0, 1] float range to a percentage integer, with a floor of 1 applied to preserve non-zero but sub-percent signals.

---

### 1.8 Middleware and Error Handling

The FastAPI application registers two middleware layers:

- **`CORSMiddleware`**: configured with `allow_origins=["*"]` to permit browser extension requests from any origin.
- **Trailing-slash normalisation middleware**: strips trailing slashes to prevent HTTP 307 redirects.

A global exception handler (`sqlalchemy_exception_handler`) intercepts unhandled exceptions at the application level and maps `IntegrityError` to HTTP 409 and `OperationalError` to HTTP 503. Within `submit_job`, a local `try/except` block provides finer-grained handling: `IntegrityError` triggers a `db.rollback()` and raises HTTP 409, whilst all other exceptions trigger `db.rollback()` and raise HTTP 500. The `get_retrieval_result` endpoint separates `HTTPException` re-raises from general exception handling to avoid masking timeout responses.

---

## 2. Results & Analysis

### 2.1 Duplicate Handling Effectiveness

The three-branch deduplication strategy provides meaningful protection against redundant pipeline executions under normal operating conditions. For the common case of a user re-submitting a recently analysed URL, the cache-hit branch returns in a single database read and one Redis `HEXISTS` call, adding negligible overhead. The stale-job threshold of 15 minutes represents a pragmatic balance: it is long enough to absorb typical pipeline processing times (scrape → NLP → retrieval) whilst short enough to permit resubmission after genuine failures.

A notable limitation is that the algorithm does not employ database-level row locking or optimistic concurrency control. Under simultaneous concurrent submissions of the same URL from multiple clients, both requests may pass the `get_article_by_url()` check before either has committed an `Article` record, resulting in a duplicate insert and a subsequent `IntegrityError` on the second writer. The current implementation handles this gracefully via the HTTP 409 response, but the second client receives an error rather than a transparent redirect to the in-progress job.

---

### 2.2 Fast-Path Latency Impact

The fast-path optimisation — bypassing the web scraper and NLP service by publishing directly to `user:to.be.retrieval` with cached article data — has a qualitatively significant impact on response latency for repeat URLs. The standard pipeline path traverses at minimum four service boundaries (API → Scraper → NLP → Retrieval), each involving Redis stream round-trips and substantial computation (HTML fetching, sentence embedding, named entity recognition, bias classification). The fast path reduces this to a single service boundary (API → Retrieval), with the retrieval service reading pre-computed embeddings from pgvector rather than recomputing them. In terms of pipeline stages, this eliminates two of the four processing stages, which represent the most computationally expensive components.

---

### 2.3 Job State Machine Robustness

The job state machine (`PENDING` → `COMPLETE` / `FAILED`) is enforced through string comparisons against `JobStatus` enum values stored in the `job` table. The absence of an explicit `PROCESSING` state at the database level means that jobs in active pipeline processing remain in the `PENDING` state until the retrieval layer writes a completion record and updates the job status. This design simplifies the state model but means that the staleness heuristic is the only mechanism distinguishing an in-flight job from a silently failed one. A 15-minute threshold accommodates expected pipeline durations but does not differentiate between slow and failed jobs at the API level.

---

### 2.4 Polling Model vs. Real-Time Delivery

The result retrieval endpoint employs a synchronous long-poll model: the client receives a response only once the result is available or the timeout expires. This approach avoids the complexity of WebSocket lifecycle management and is well-suited to the browser extension polling pattern described in the expected response specification. The drawback is that each in-flight poll holds an open HTTP connection and occupies an async worker for up to 60 seconds, which can constrain throughput under concurrent load. A WebSocket or Server-Sent Events model would reduce connection overhead but would require state management for connection tracking and reconnection logic on the client side.

---

### 2.5 Error Patterns and Response Reliability

The layered error handling strategy produces consistent, semantically appropriate HTTP status codes across failure modes:

- **HTTP 409**: raised on `IntegrityError` (concurrent duplicate URL insert).
- **HTTP 404**: raised when a job or result is not found within the polling timeout.
- **HTTP 500**: raised on unexpected exceptions during job submission or result retrieval; always preceded by a `db.rollback()` to prevent partial transaction commits.
- **HTTP 503**: raised at the global handler level for database connectivity failures (`OperationalError`).

A structural gap exists in the result retrieval path: if the `save_data_result.article_entry_id` field is absent from the Redis hash payload, the endpoint raises an untyped `Exception` which is caught and re-raised as HTTP 500. This case can occur if the retrieval service writes a partial result. More expressive error codes (e.g., HTTP 422 or HTTP 202 with a `processing` status) would improve client-side error recovery.

---

### 2.6 Scalability Considerations

The API gateway is horizontally scalable: each instance is stateless with respect to pipeline execution, and all shared state is held in PostgreSQL and Redis. However, several design characteristics constrain scalability in practice. The synchronous SQLAlchemy session model (using `psycopg2`) means that each request holds a database connection for its duration; under high concurrency, connection pool exhaustion becomes a limiting factor. Migrating to an async ORM (e.g., SQLAlchemy async with `asyncpg`) and async database sessions would improve connection efficiency significantly for the long-poll result endpoint, which holds connections open for up to 60 seconds per request.

The `RedisPublisherRouter` and `RedisHashStore` instances are constructed at module level and shared across requests, which is appropriate for Redis connection reuse but means that Redis connection failures affect all concurrent requests simultaneously. The current absence of circuit-breaking or fallback logic means that Redis unavailability propagates as HTTP 500 errors to all clients.
