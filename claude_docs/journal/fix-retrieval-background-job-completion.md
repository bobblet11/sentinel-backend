---
## [2026-04-17 00:00] Fix Background Job Completion in Retrieval Layer and Docker Compose Default Streams

**Date**: April 17, 2026 at 12:00 AM UTC
**Agent**: `claude-inline`
**Branch**: `main`
**Triggered By**: Two inline bug fixes requested by user — background jobs never marked COMPLETE in PostgreSQL (Bug #1), and bare `docker-compose up` without an env file missing background stream consumption (Bug #3).

### Summary
Background jobs were returning early from the retrieval service without being persisted to PostgreSQL, breaking the fast-path lookup that checks for already-completed background articles. Separately, the default `INPUT_STREAMS` value in the Docker Compose file only listed the user stream, so a bare deployment without an env file would silently ignore all background jobs.

### Files Changed
| File Path | Change Type | Description |
|-----------|-------------|-------------|
| `microservices/retrieval_layer/services/retrieval_service.py` | Modified | Moved `original_article_id` extraction before the background-job early-return guard, and added a `_save_job_into_postgres(db, message)` call before that early return so background jobs are marked COMPLETE in PostgreSQL. |
| `docker/compose/docker-compose.yml` | Modified | Changed the default value of `INPUT_STREAMS` for both `retrieval-layer-service` (GPU, line 345) and `retrieval-layer-service-cpu` (line 410) from `user:to.be.retrieval` to `user:to.be.retrieval,background:to.be.retrieval`. |

### Details
- **Bug #1 (retrieval_service.py)**: The early-return path for background jobs skipped the PostgreSQL write entirely. The fast-path query (used before scraping to detect already-processed articles) checks for a COMPLETE status in PostgreSQL — without this write, every background article appeared unprocessed and was re-ingested indefinitely. Fix: extract `original_article_id` before the guard, then call `_save_job_into_postgres` immediately before returning.
- **Bug #3 (docker-compose.yml)**: Both the GPU and CPU retrieval service definitions had `INPUT_STREAMS` defaulting to only `user:to.be.retrieval`. Any developer doing a bare `docker-compose up` without a populated env file would stand up a retrieval layer that silently discards all background ingestor jobs. Fix: both service default values now include `background:to.be.retrieval` as a comma-separated second stream, matching the intended prioritised-stream architecture.
- No new environment variables or stream names were introduced; the `background:to.be.retrieval` stream already exists in the architecture.

### Pipeline Impact
- **Retrieval stage**: High impact — background jobs now correctly reach a terminal COMPLETE state in PostgreSQL, unblocking the duplicate-detection fast path.
- **Ingestor / background pipeline**: High impact — background articles will no longer be repeatedly re-queued due to a missing completion record.
- **Docker deployment**: Medium impact — bare deployments now consume both user and background streams as intended, without requiring a custom env file.
- E2E stability: these are correctness fixes; the user stream happy path is unaffected.

---
