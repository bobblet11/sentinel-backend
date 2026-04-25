# Topic Clustering Integration Plan

## Context

The topic clustering POC (`scripts/topic_clustering/poc_cluster.py`) validates that BERTopic can assign Sentinel articles to 8 predefined topic categories (Politics, World, Technology, Health, Science, Business, Entertainment, Sports). This plan integrates topic assignment into the production pipeline so that:

1. All existing articles in the DB are backfilled with a topic
2. Every new article gets a topic assigned as it flows through the pipeline

The approach avoids BERTopic in the production pipeline (it is batch-only and heavy). Instead, we use the **same SentenceTransformer already loaded by the NLP service** (`all-mpnet-base-v2`) to compute cosine similarity against pre-computed topic label embeddings — this is equivalent to BERTopic's zero-shot portion but runs on a single document with no refitting.

---

## Architecture Overview

```
NLP Service (new Stage 9: TopicClassifier)
  → embeds "title + top 2 claims" using existing EMBEDDING model
  → cosine similarity against 8 pre-computed topic label embeddings
  → writes topic_label + topic_confidence to NLPResult / MessagePayload

Retrieval Layer (after _save_data_into_postgres)
  → reads topic_label + topic_confidence from StreamMessage
  → upserts into article_topic table (same DB transaction)

Backfill script (one-time)
  → same SentenceTransformer + cosine similarity logic
  → seeds topic table with 8 predefined topics
  → writes article_topic rows for all existing articles
```

---

## Step 1 — DB Tables

**New file:** `microservices/db/migrations/002_add_topic_tables.sql`

```sql
CREATE TABLE IF NOT EXISTS topic (
    id   SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS article_topic (
    id          SERIAL PRIMARY KEY,
    article_id  INTEGER NOT NULL REFERENCES article(id) ON DELETE CASCADE,
    topic_id    INTEGER NOT NULL REFERENCES topic(id),
    confidence  FLOAT,
    assigned_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (article_id)   -- one topic per article; use upsert to update
);

CREATE INDEX IF NOT EXISTS idx_article_topic_article_id ON article_topic(article_id);
CREATE INDEX IF NOT EXISTS idx_article_topic_topic_id   ON article_topic(topic_id);

-- Seed predefined topics
INSERT INTO topic (name) VALUES
  ('Politics'),('World'),('Technology'),('Health'),
  ('Science'),('Business'),('Entertainment'),('Sports')
ON CONFLICT (name) DO NOTHING;
```

**Modify:** `microservices/retrieval_layer/db/models.py`
- Add `Topic` ORM model (id, name UNIQUE)
- Add `ArticleTopic` ORM model (id, article_id FK, topic_id FK, confidence, assigned_at)
- Add `Article.article_topic` backref relationship
- `ensure_schema_compatibility()` in `session.py` calls `Base.metadata.create_all()` — new tables are picked up automatically on next service start

---

## Step 2 — StreamMessage Schema Extension

**Modify:** `common/models/api/redis_models.py`

Add two optional fields to `NLPResult` (line ~164):
```python
topic_label: Optional[str] = None
topic_confidence: Optional[float] = None
```

Add the same two fields to `MessagePayload` (line ~199), alongside `bias_profile`:
```python
topic_label: Optional[str] = None
topic_confidence: Optional[float] = None
```

Update `set_nlp_result()` (line ~320) to propagate these fields — follow the same pattern as `bias_profile`:
```python
if nlp_result.topic_label is not None:
    self.data.payload.topic_label = nlp_result.topic_label
    self.data.payload.topic_confidence = nlp_result.topic_confidence
```

---

## Step 3 — TopicClassifier NLP Component

**New file:** `microservices/nlp/components/topic_classifier.py`

- Subclass `ArticleProcessor` (same base as `BiasDetector`)
- At `__init__`: retrieve `SentenceTransformer` from `model_manager.get("EMBEDDING")` — no new model registration needed, reuses the existing `all-mpnet-base-v2` already loaded by `Embedder`
- Pre-compute topic label embeddings once at init: embed the 8 topic name strings, store as a `(8, 768)` numpy matrix
- `run()`:
  1. Get `result.claims_in_article` (already populated by Stage 7)
  2. Sort by `claim.confidence` desc, take top 2 `decontextualised_claim_text`
  3. Build doc: `(title + " " + top_claims).strip()[:400]`
  4. Embed doc using the SentenceTransformer
  5. Cosine similarity between doc embedding and topic matrix → pick argmax
  6. If best similarity < `TOPIC_SIMILARITY_THRESHOLD` → `topic_label = "Other"`
  7. Write `result.topic_label` and `result.topic_confidence`
  8. Call `message.set_nlp_result(result)`
- Graceful degradation: if model unavailable or exception, log warning and continue (topic stays None)

**Modify:** `microservices/nlp/config.py`
- Add `TOPIC_SIMILARITY_THRESHOLD = float(os.environ.get("NLP_TOPIC_SIMILARITY_THRESHOLD", "0.3"))`
- Add `TOPIC_LABELS` list constant (the 8 predefined topics — same list as POC)

---

## Step 4 — Wire TopicClassifier into ClaimExtraction

**Modify:** `microservices/nlp/components/claimextract.py`

Follow the same lazy init pattern used for `BiasDetector` (lines 87-89):
```python
self._topic_device_config = device_config
self._topic_model_manager = model_manager
self._topic_classifier = None  # lazy init
```

Add Stage 9 in `run()` after BiasDetector (Stage 8), with same try/except pattern:
```python
# ── Stage 9 — Topic Classification ──────────────────────────────────
t = time.time()
try:
    if self._topic_classifier is None:
        from microservices.nlp.components.topic_classifier import TopicClassifier
        self._topic_classifier = TopicClassifier(
            device_config=self._topic_device_config,
            model_manager=self._topic_model_manager,
        )
    self._topic_classifier.run(article, message, options)
except Exception as e:
    logger.warning("ClaimExtraction [Stage 9 TopicClassifier] failed: %s", e)
    # Non-fatal — topic stays None
logger.info("[Stage 9 | TopicClassifier] complete in %.2fs", time.time() - t)
```

Update the pipeline docstring to document Stage 9.

---

## Step 5 — Retrieval Layer Writes Topic to DB

**Modify:** `microservices/retrieval_layer/storage/dtos.py`
- Add `UpsertArticleTopic` DTO: `article_id`, `topic_label`, `topic_confidence`

**Modify:** `microservices/retrieval_layer/storage/crud.py`
- Add `upsert_article_topic(db, dto: UpsertArticleTopic)`:
  - Look up `Topic` row by `name` — if not found, insert it (handles "Other" or future topics)
  - `INSERT INTO article_topic ... ON CONFLICT (article_id) DO UPDATE SET topic_id=..., confidence=..., assigned_at=NOW()`

**Modify:** `microservices/retrieval_layer/services/retrieval_service.py`
- Inside `_save_data_into_postgres()`, after saving the article, add:
```python
if message.data.payload.topic_label:
    upsert_article_topic(db, UpsertArticleTopic(
        article_id=article_db_id,
        topic_label=message.data.payload.topic_label,
        topic_confidence=message.data.payload.topic_confidence,
    ))
```
- This runs inside the existing `get_db_transaction()` context — atomic with the article/claim writes

---

## Step 6 — Backfill Script

**New file:** `scripts/topic_clustering/backfill_topics.py`

- Connects to DB using same `load_env()` / `get_engine()` from `poc_cluster.py`
- Fetches all articles with title + top 2 claims (same SQL as `poc_cluster.py`)
- Loads `all-mpnet-base-v2` SentenceTransformer (with CUDA auto-detect, same as `poc_cluster.py`)
- Computes topic assignments using the same cosine similarity logic as `TopicClassifier`
- Seeds `topic` table (8 predefined topics) using `INSERT ... ON CONFLICT DO NOTHING`
- Batch-upserts into `article_topic` using `INSERT ... ON CONFLICT (article_id) DO UPDATE`
- Logs progress every 100 articles
- Safe to re-run (idempotent upserts)
- Accepts `--env-file`, `--batch-size`, `--threshold` CLI args

---

## Step 7 — Environment Variables

Add to `configs/deploy-local/.env` and `configs/aws/.env`:
```
NLP_TOPIC_SIMILARITY_THRESHOLD=0.3
```

No new model downloads required — reuses `all-mpnet-base-v2` already in `HF_HOME`.

---

## Critical Files

| Action | File |
|---|---|
| NEW migration SQL | `microservices/db/migrations/002_add_topic_tables.sql` |
| NEW ORM models | `microservices/retrieval_layer/db/models.py` |
| NEW NLP component | `microservices/nlp/components/topic_classifier.py` |
| NEW backfill script | `scripts/topic_clustering/backfill_topics.py` |
| MODIFY StreamMessage schema | `common/models/api/redis_models.py` |
| MODIFY NLP orchestrator | `microservices/nlp/components/claimextract.py` |
| MODIFY NLP config | `microservices/nlp/config.py` |
| MODIFY Retrieval crud | `microservices/retrieval_layer/storage/crud.py` |
| MODIFY Retrieval dtos | `microservices/retrieval_layer/storage/dtos.py` |
| MODIFY Retrieval service | `microservices/retrieval_layer/services/retrieval_service.py` |
| MODIFY env files | `configs/deploy-local/.env`, `configs/aws/.env` |

---

## Verification

1. **Run migration** against local Docker postgres:
   ```bash
   docker exec sentinel-pg-local psql -U postgres -d postgres \
     -f microservices/db/migrations/002_add_topic_tables.sql
   ```
   Confirm `topic` table has 8 rows and `article_topic` table exists.

2. **Run backfill**:
   ```bash
   scripts/topic_clustering/.venv/bin/python -m scripts.topic_clustering.backfill_topics \
     --env-file configs/local/.env
   ```
   Confirm `article_topic` has rows. Spot-check a few article → topic assignments.

3. **Run NLP unit tests**:
   ```bash
   pytest tests/
   ```

4. **Deploy locally and submit a test job** via the API:
   ```bash
   curl -X POST http://localhost:8001/api/v1/jobs -d '{"url": "..."}'
   ```
   After job completes, query:
   ```sql
   SELECT a.title, t.name, at.confidence
   FROM article a
   JOIN article_topic at ON at.article_id = a.id
   JOIN topic t ON t.id = at.topic_id
   ORDER BY a.id DESC LIMIT 5;
   ```
   Confirm new article has a topic assigned.
