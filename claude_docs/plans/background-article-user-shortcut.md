# Plan: Background-Article User Shortcut

## Problem

When a user submits a URL that was **already processed by a background ingestor job**, the system re-runs the full pipeline (scrape → NLP → retrieval) even though the article's claims, embeddings, entities, and bias profile are already stored in PostgreSQL. This wastes 60–120 seconds of GPU time per article and provides a degraded user experience.

### Root Cause

`submit_job` in `jobs.py` calls:
```python
get_latest_job_for_article(db, article_id, job_type="user")
```
It only searches for **user** jobs. Background jobs are invisible to this check, so a re-analysis is always triggered when the article was ingested via the background pipeline.

Background jobs also do **not** write results to the Redis hash store (line 562–564 in `retrieval_service.py`):
```python
if message.type == JobType.BACKGROUND:
    self.logger.info("Background job complete uid=%s", message.header.uid)
    return message
```
So a user job can't reuse a background job's hash store entry — but all the raw data (claims, embeddings, bias) **is** persisted to PostgreSQL.

---

## Solution: Fast-Path to Retrieval

When a COMPLETE background job exists for the article, create a new user job but publish it **directly to `user:to.be.retrieval`** (skipping `user:to.be.scraped` → NLP entirely). The retrieval service detects a `retrieve_from_db=True` flag, loads the article's existing claims and bias profile from PostgreSQL, and runs only the evidence retrieval + NLI stage.

### New Decision Flow in `submit_job`

```
User POST /api/v1/jobs
  ↓
Article in DB?           ─── No  ──→ Full pipeline (unchanged)
  ↓ Yes
Complete USER job with
  hash store result?     ─── Yes ──→ Return it immediately (unchanged)
  ↓ No
Active (non-stale)
  USER job pending?      ─── Yes ──→ Return it (unchanged)
  ↓ No
Complete BACKGROUND job? ─── No  ──→ Full pipeline (retry, unchanged)
  ↓ Yes
Create user job
Publish to user:to.be.retrieval  ← NEW fast-path
  ↓
Retrieval service: retrieve_from_db=True
  → Load article claims + bias from PostgreSQL
  → Run filter_step / similarity_step / classification_step (unchanged)
  → Write result to hash store
  → Mark job COMPLETE
```

---

## Changes Required

### 1. `common/models/api/redis_models.py`

Add two fields to `MessagePayload`:

```python
class MessagePayload(BaseModel):
    ...
    # fast-path flag: skip scrape+NLP, load claims from DB
    retrieve_from_db: bool = False
    article_db_id: int | None = None
```

Both default to `False`/`None` so all existing code is unaffected.

---

### 2. `microservices/api/app/crud/crud_job.py`

Add a helper to find completed background jobs:

```python
def get_latest_completed_background_job_for_article(
    db: Session, article_id: int
) -> Job | None:
    return (
        db.query(Job)
        .filter(
            Job.article_id == article_id,
            Job.type == JobType.BACKGROUND.value,
            Job.status == JobStatus.COMPLETE.value,
        )
        .order_by(Job.created_at.desc())
        .first()
    )
```

---

### 3. `microservices/api/app/services/redis_queue.py`

Add a retrieval publisher and a fast-path publish function.

The stream name `"user:to.be.retrieval"` is hardcoded — consistent with the existing pattern where `"background:to.be.scraped"` is hardcoded on line 16 of the same file. No new env var or docker-compose entry is needed.

```python
from common.redis_client.publisher import RedisPublisher

retrieval_publisher = RedisPublisher(stream="user:to.be.retrieval")

def publish_job_to_retrieval(job: Job, article: Article) -> None:
    """Fast-path: publish a user job directly to retrieval (skip scrape + NLP)."""
    payload = MessagePayload(
        article_url=article.url,
        title=article.title,
        news_outlet=article.outlet.name if article.outlet else None,
        publish_date=article.publishedAt.isoformat() if article.publishedAt else None,
        retrieve_from_db=True,
        article_db_id=cast(int, article.id),
    )
    message = Message(
        header=MessageHeader(
            id=job.id,
            uid=str(job.uid),
            created_at=datetime.datetime.now().isoformat(),
            status=JobStatus.PENDING,
            type=job.type,
        ),
        payload=payload,
        stage_timestamps=[],
    )
    message = add_timestamp_to_message(message=message, stage_name=JobStage.INGESTED)
    retrieval_publisher.publish_one(message.model_dump(mode='json'))
```

---

### 4. `microservices/api/app/api/v1/endpoints/jobs.py`

Add the fast-path branch in `submit_job`, after the existing user-job checks:

```python
from microservices.api.app.crud.crud_job import (
    create_job,
    get_latest_job_for_article,
    get_latest_completed_background_job_for_article,  # new
)
from microservices.api.app.services.redis_queue import publish_job, publish_job_to_retrieval  # new

# Inside submit_job, after the existing_job checks (before falling through to full pipeline):
background_job = get_latest_completed_background_job_for_article(
    db=db, article_id=cast(int, existing_article.id)
)
if background_job:
    fast_path_job: Job = create_job(db=db, job_in=job_in, article_id=cast(int, existing_article.id))
    publish_job_to_retrieval(fast_path_job, existing_article)
    db.commit()
    logger.info(
        "Background-analyzed article fast-pathed to retrieval id=%s uid=%s url=%s",
        fast_path_job.id,
        fast_path_job.uid,
        existing_article.url,
    )
    return fast_path_job

# ... rest of existing flow (retry_job or full new job)
```

Exact placement: this block goes immediately **after** the stale-job check (line ~194), before `retry_job = create_job(...)`.

---

### 5. `microservices/retrieval_layer/storage/crud.py`

Add a query to load an article's claims (with entities) and sentiment:

```python
from typing import Tuple

def get_article_claims_with_bias(
    db: Session, article_id: int
) -> Tuple[List[Claim], Optional[SentimentAnalysis]]:
    """Load stored claims (with entities) and sentiment for a background-analyzed article."""
    claim_rows = (
        db.execute(
            select(Claim)
            .options(joinedload(Claim.entities))
            .where(Claim.article_id == article_id)
        )
        .scalars()
        .unique()
        .all()
    )

    article_row = db.execute(
        select(Article)
        .options(joinedload(Article.sentiment))
        .where(Article.id == article_id)
    ).scalar_one_or_none()

    sentiment = article_row.sentiment if article_row else None
    return list(claim_rows), sentiment
```

---

### 6. `microservices/retrieval_layer/services/retrieval_service.py`

#### Add `_load_claims_from_db` method

Converts DB ORM rows into the `Claim` and `BiasProfile` redis dataclasses that `_retrieve_evidence` expects:

```python
def _load_claims_from_db(
    self, db: Session, article_id: int
) -> Tuple[List[Claim], Optional[BiasProfile]]:
    from microservices.retrieval_layer.storage.crud import get_article_claims_with_bias
    from common.models.api.redis_models import Claim as ClaimRedis, Entity as EntityRedis

    claim_rows, sentiment = get_article_claims_with_bias(db, article_id)

    redis_claims: List[Claim] = []
    for row in claim_rows:
        entities = [
            EntityRedis(
                entity_text=e.name,
                type_of_entity=e.type or "",
                start_char=0,
                end_char=0,
            )
            for e in row.entities
        ]
        redis_claims.append(
            ClaimRedis(
                confidence=row.centrality_score or 0.5,
                source_sentence_indices=[],
                decontextualised_claim_text=row.decontextualised_claim or row.original_sentence,
                decontextualised_claim_embedding=(
                    list(row.decontextualised_embedding)
                    if row.decontextualised_embedding is not None
                    else None
                ),
                NER_entities=entities,
            )
        )

    bias_profile = None
    if sentiment:
        bias_profile = BiasProfile(
            bias_category=sentiment.bias_category or "center",
            bias_analysis_confidence=sentiment.bias_analysis_confidence or 0.0,
            sentiment_category=sentiment.sentiment_category,
            sentiment_analysis_confidence=sentiment.sentiment_analysis_confidence or 0.0,
        )

    self.logger.info(
        "Fast-path: loaded %d claims from DB for article_id=%d",
        len(redis_claims),
        article_id,
    )
    return redis_claims, bias_profile
```

#### Modify `_process_message` to branch on `retrieve_from_db`

```python
def _process_message(self, message: StreamMessage) -> StreamMessage:
    with get_db_transaction() as db:

        if message.data.payload.retrieve_from_db:
            # Fast-path: article already analyzed by background job.
            # Skip _save_data_into_postgres (would overwrite DB with empty NLP data).
            original_article_id = message.data.payload.article_db_id or 0
            claims, bias_profile = self._load_claims_from_db(db, original_article_id)
            message.data.payload.claims_in_article = claims
            message.data.payload.bias_profile = bias_profile
            save_data_result = {"article_entry_id": original_article_id}
        else:
            message.add_timestamp(JobStage.SAVE_DATA_IN)
            save_data_result = self._save_data_into_postgres(db, message)
            message.add_timestamp(JobStage.SAVE_DATA_OUT)

            if message.type == JobType.BACKGROUND:
                self.logger.info("Background job complete uid=%s", message.header.uid)
                return message

            original_article_id = save_data_result.get("article_entry_id") or 0

        # Both paths continue here for user jobs:
        message.add_timestamp(JobStage.RETRIEVE_EVIDENCE_IN)
        claim_evidence_matches, related_articles = self._retrieve_evidence(
            db, message, original_article_id
        )
        message.add_timestamp(JobStage.RETRIEVE_EVIDENCE_OUT)

        message.add_timestamp(JobStage.UPDATE_JOB_IN)
        save_job_result = self._save_job_into_postgres(db, message)
        message.add_timestamp(JobStage.UPDATE_JOB_OUT)

        # ... rest of method unchanged (RetrievalResult, stats, hash store write)
```

---

## Edge Cases

| Scenario | Behavior |
|---|---|
| Background job is COMPLETE but has 0 claims (short/broken article) | Fast-path runs with empty claims → empty evidence results. Consistent with normal NLP producing 0 claims. |
| `article_db_id` points to missing article | `get_article_claims_with_bias` returns `([], None)` → empty claims, no bias. Logs warning. |
| Background job still PENDING/FAILED | `get_latest_completed_background_job_for_article` returns `None` → full pipeline runs as normal. |
| `article.outlet` not loaded (lazy) | SQLAlchemy lazy-loads within the open DB session in `submit_job`. Safe. |
| Concurrent duplicate user submissions | Second submission finds the first user job as PENDING (unchanged dedup logic). |

---

## Files Changed (6 total)

No env var, docker-compose, or `.env` changes needed. `"user:to.be.retrieval"` is hardcoded in `redis_queue.py`, consistent with the existing `"background:to.be.scraped"` hardcoded pattern in that file.

| File | Change |
|---|---|
| `common/models/api/redis_models.py` | Add `retrieve_from_db` + `article_db_id` to `MessagePayload` |
| `microservices/api/app/crud/crud_job.py` | Add `get_latest_completed_background_job_for_article()` |
| `microservices/api/app/services/redis_queue.py` | Add `retrieval_publisher` (hardcoded stream) + `publish_job_to_retrieval()` |
| `microservices/api/app/api/v1/endpoints/jobs.py` | Add fast-path branch in `submit_job()` |
| `microservices/retrieval_layer/storage/crud.py` | Add `get_article_claims_with_bias()` |
| `microservices/retrieval_layer/services/retrieval_service.py` | Add `_load_claims_from_db()` + fast-path branch in `_process_message()` |
