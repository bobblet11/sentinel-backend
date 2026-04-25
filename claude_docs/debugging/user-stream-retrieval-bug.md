# User Stream → Retrieval Bug: Audit & Fix Plan

## Symptom

Background jobs reach the retrieval layer and are processed.  
User jobs do **not** reach the retrieval layer — results are never stored and the client polls forever.

A secondary symptom: when the API detects an article was "already analyzed" (fast-path), the job is published to `user:to.be.retrieval` but still never surfaces a result.

---

## Root Cause Summary

There are **four bugs** identified across `retrieval_service.py` and `service_template.py`. Bugs #1 and #2 are the critical blockers.

---

## Bug #1 — CRITICAL: Background Jobs Never Marked COMPLETE in DB

**File:** `microservices/retrieval_layer/services/retrieval_service.py` ~line 624

**What happens:**  
`_process_message` contains an early-return for background jobs:
```python
if message.type == JobType.BACKGROUND:
    return message
```
This returns before calling `_save_job_into_postgres`, which is the only function that calls `finalise_and_complete_job` and sets the job status to `COMPLETE`.

**Impact:**  
Background jobs stay in `PENDING` status in PostgreSQL forever.  
The fast-path query in `crud_job.py`:
```python
get_latest_completed_background_job_for_article()
# filters: type=BACKGROUND, status=COMPLETE
```
…can **never** return a result. The fast-path is permanently broken regardless of how many background jobs have been processed.

**Fix:** Call `_save_job_into_postgres` for background jobs before (or instead of) the early-return.

---

## Bug #2 — CRITICAL: Sequential Mode Never Writes to Hash Store for User Jobs

**File:** `microservices/retrieval_layer/services/retrieval_service.py`, lines 487–533  
**File:** `docker/compose/docker-compose.yml`, line 368 — `MAX_WORKERS=${RETRIEVAL_MAX_WORKERS:-1}`  
**File:** `configs/deploy-local/.env` — `RETRIEVAL_MAX_WORKERS=2`

**What happens:**  
`RetrievalService` overrides `_process_and_publish_worker` (concurrent path, lines 445–480) to call:
```python
self.hash_store.set(message.uid, payload)
```
This is how user results are stored for the API to retrieve.

However, `_process_batch_sequentially` (lines 487–533) was separately re-implemented directly in `RetrievalService` (overriding the base class) and **also** contains the `hash_store.set` call (lines 505–510). So the sequential path is actually correct in the override.

**Re-check:** `deploy-local/.env` sets `RETRIEVAL_MAX_WORKERS=2`, which means retrieval runs in **concurrent mode** in practice. The sequential path bug concern from the audit was based on the default `MAX_WORKERS=1` — with `MAX_WORKERS=2` the concurrent path (`_process_and_publish_worker`) is used instead.

**Remaining concern:** If `MAX_WORKERS=1` is ever used (e.g., in production or a different config), the sequential override in `RetrievalService` does call `hash_store.set` correctly. Both paths are handled. This bug is **lower priority** than initially assessed.

**Still verify:** That `hash_store.set` is actually being reached at runtime — if `_process_message` throws an exception before returning, neither path reaches the store call. Check retrieval logs for exceptions.

---

## Bug #3 — Docker Compose Default Missing Background Stream

**File:** `docker/compose/docker-compose.yml`, lines 345 and 410

```yaml
INPUT_STREAMS=${RETRIEVAL_INPUT_STREAMS:-user:to.be.retrieval}
```

The fallback only includes the user stream. If the `.env` file is not loaded (e.g., a bare `docker-compose up` without the env file), background jobs would never be consumed by retrieval.

Both `configs/deploy-local/.env` and `configs/aws/.env` correctly set:
```
RETRIEVAL_INPUT_STREAMS=user:to.be.retrieval,background:to.be.retrieval
```
So this only bites in bare Docker runs without env files, but the default should be fixed.

**Fix:** Change default to `:-user:to.be.retrieval,background:to.be.retrieval` on lines 345 and 410.

---

## Bug #4 — `consume_pending` Can Starve New User Messages

**File:** `common/service/service_template.py`, `_process_a_batch`

**What happens:**  
On every poll cycle, the service calls `consume_pending()` first (reads `XREADGROUP 0-0` for all streams — returns all unacknowledged messages this consumer has claimed). Only if that returns empty does it call `_get_raw_messages()` to fetch new messages.

If there are stale pending messages from a previous crash (e.g., NLP or retrieval died mid-message), `consume_pending()` will keep returning them on every cycle. New user messages sit in the stream unconsumed.

`is_cut_and_paste_mode=True` means failures are ack+deleted, which should drain stale pending — but if the ack itself fails, messages stay stuck indefinitely.

**How to check:**
```bash
redis-cli XPENDING user:to.be.retrieval default - + 10
redis-cli XPENDING user:to.be.nlp default - + 10
```
If these return entries, stale pending messages are present and blocking new consumption.

---

## Most Likely Immediate Cause

Given that background jobs work but user jobs don't:

1. **Check NLP → retrieval handoff for user jobs.** NLP routes user jobs to `USER_OUTPUT_STREAM=user:to.be.retrieval`. If NLP is failing on user jobs (but not background jobs), they end up in a failure stream instead.

   ```bash
   redis-cli XLEN user:to.be.retrieval       # should increase after submitting a user job
   redis-cli XLEN failure:to.be.nlp           # should be 0 for user jobs
   redis-cli XLEN failure:to.be.retrieval     # check for retrieval failures too
   ```

2. **Check for stale pending messages** (Bug #4) blocking retrieval from seeing new user messages.

3. **Confirm `_process_message` doesn't throw** for user jobs in retrieval — if it does, `hash_store.set` is never reached and the result is lost even if the message was consumed.

---

## Files to Fix (Priority Order)

| Priority | File | Change |
|---|---|---|
| 1 (CRITICAL) | `microservices/retrieval_layer/services/retrieval_service.py` | Call `_save_job_into_postgres` for background jobs before early-return |
| 2 (INVESTIGATE) | Retrieval + NLP logs | Confirm user jobs are arriving at retrieval and not throwing exceptions |
| 3 | `docker/compose/docker-compose.yml` lines 345, 410 | Fix default `INPUT_STREAMS` to include both streams |
| 4 | Redis inspection | Clear stale pending messages if Bug #4 is confirmed |

---

## Fast-Path Status

The fast-path code in `jobs.py` (lines 200–215) is structurally correct. It:
1. Checks for a completed background job for the URL (`get_latest_completed_background_job_for_article`)
2. Creates a user job
3. Publishes to `user:to.be.retrieval` with `retrieve_from_db=True` and `article_db_id`

**This will not work until Bug #1 is fixed** — no background job is ever marked `COMPLETE`, so step 1 always returns `None`.

Once Bug #1 is fixed, the fast-path should function end-to-end without any other changes.
