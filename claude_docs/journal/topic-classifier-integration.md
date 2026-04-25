---
## [2026-04-16 18:35] Topic Classifier Integration — Split 7: API Topic Endpoints

**Date**: April 16, 2026 at 6:35 PM UTC
**Agent**: `claude-inline`
**Branch**: `features/cluster`
**Triggered By**: Split 7 (final split) of the topic classifier integration — expose article_topic table data via two new read-only API endpoints.

### Summary
Completes the topic classifier integration by adding read-only ORM models for `Topic` and `ArticleTopic` to the API service and wiring up two new endpoints: `GET /api/v1/topics` (list all 9 topics with article counts) and `GET /api/v1/topics/{topic_name}/articles` (paginated articles per topic, sorted by confidence). No existing `/jobs` endpoints are modified — purely additive.

### Files Changed
| File Path | Change Type | Description |
|-----------|-------------|-------------|
| `microservices/api/app/models/article.py` | Modified | Added `Float` to SQLAlchemy imports; added `Topic` and `ArticleTopic` ORM models; added `topic_assignment` relationship to `Article` (`uselist=False`) — read-only mirror of retrieval-layer schema |
| `microservices/api/app/api/v1/endpoints/topics.py` | Created | `GET /api/v1/topics` lists all 9 topics with `article_count` via outer join; `GET /api/v1/topics/{topic_name}/articles` returns paginated articles sorted by `confidence DESC` with 404 on unknown topic and case-insensitive name matching; uses existing `get_db()` session dependency |
| `microservices/api/app/api/v1/api.py` | Modified | Imported `topics` endpoint module; registered topics router with `prefix=/topics` and `tag=topics` |

### Details
- `Topic` and `ArticleTopic` ORM models are **read-only** — they mirror tables written by the NLP service and backfill script; the API service never writes to them.
- `topic_assignment` on `Article` uses `uselist=False` enforcing the one-topic-per-article constraint at the ORM layer.
- `GET /topics` uses an outer join so all 9 canonical topics always appear in the response even when `article_count` is 0 — important for front-end dropdowns that must show the full topic list.
- Case-insensitive topic name matching in `GET /topics/{topic_name}/articles` prevents 404s from capitalisation mismatches.
- Follows the same `get_db()` session dependency pattern established in `jobs.py` — no new session management plumbing required.
- This is the **final split** of the topic classifier integration; the full feature (model → NLP pipeline → DB schema → backfill → API) is now complete.

### Pipeline Impact
API layer only. No changes to scrape, NLP, or retrieval stages. E2E stability unaffected — additive endpoints only.

---
## [2026-04-16 15:44] Topic Classifier Integration — Split 6: Backfill Script

**Date**: April 16, 2026 at 3:44 PM UTC
**Agent**: `claude-inline`
**Branch**: `features/cluster`
**Triggered By**: Split 6 of the topic classifier integration — add a re-runnable backfill script to assign topics to articles that pre-date the NLP pipeline topic assignment.

### Summary
Adds `scripts/topic_clustering/backfill_topics.py`, a gap-aware, production-safe CLI tool that assigns topic rows to articles missing from the `article_topic` table. Designed to be idempotent and safely re-runnable on a live DB: subsequent runs after full coverage are near-instant due to the `LEFT JOIN … WHERE article_topic.article_id IS NULL` gap filter. A `--force` flag enables full reclassification (useful after threshold or description tuning), and `--dry-run` validates output without writing.

### Files Changed
| File Path | Change Type | Description |
|-----------|-------------|-------------|
| `scripts/topic_clustering/backfill_topics.py` | Created | Backfill script: gap-filling LEFT JOIN query, `--force` / `--dry-run` flags, batched processing (default 200), ON CONFLICT upsert, topic-id cache validated at startup |

### Details
- Reuses shared utilities from `poc_cluster.py`: `load_env`, `get_engine`, `load_embedding_model`, `_build_docs`, `_clean_doc`, `TOPIC_DESCRIPTIONS`, `PREDEFINED_TOPICS`, `CONFIDENCE_THRESHOLD` — no duplication of core logic.
- Topic embeddings pre-computed once at startup; articles streamed in configurable batches (default 200) to bound memory usage.
- Caches `topic_name → DB id` at startup and validates all 9 expected topics exist; exits early with a clear error if any are missing (guards against running against an un-seeded DB).
- `ON CONFLICT` upsert ensures writes are safe even if the live NLP pipeline races and inserts a row between the gap query and the write.
- Progress logged every 100 articles for observability during long-running backfills.
- CLI invocation: `python -m scripts.topic_clustering.backfill_topics --env-file configs/.env`

### Pipeline Impact
No change to live pipeline stream topology or NLP stages. Script targets the `article_topic` DB table directly — same table written by the NLP topic classifier — so it shares the upsert safety guarantee. No E2E pipeline run required; this is an offline data-repair tool.

---
## [2026-04-16 15:30] Topic Classifier Integration — Split 5: Retrieval Layer Persistence

**Date**: April 16, 2026 at 3:30 PM UTC
**Agent**: `claude-inline`
**Branch**: `newretrieval-fixes`
**Triggered By**: Split 5 of the topic classifier pipeline integration — wiring the retrieval layer to persist topic assignments produced by NLP Stage 9 into the `article_topic` DB table.

### Summary
The retrieval layer can now receive a `topic_label` from the NLP pipeline message payload and persist it into the `article_topic` table via a new `UpsertArticleTopic` DTO + CRUD function. The integration is fully non-fatal: if `topic_label` is absent (Stage 9 skipped or failed), or the referenced topic does not exist in the DB, the article/claim save proceeds normally without interruption.

### Files Changed
| File Path | Change Type | Description |
|-----------|-------------|-------------|
| `microservices/retrieval_layer/storage/dtos.py` | Modified | Added `UpsertArticleTopic` dataclass with fields `article_id: int`, `topic_label: str`, `topic_confidence: float` |
| `microservices/retrieval_layer/storage/crud.py` | Modified | Added imports for `UpsertArticleTopic`, `Topic`, `ArticleTopic`, and `text` (SQLAlchemy); added `upsert_article_topic(db, dto)` which looks up `Topic` by name then executes `INSERT INTO article_topic ON CONFLICT (article_id) DO UPDATE` and flushes; returns early (no crash) if topic label not found |
| `microservices/retrieval_layer/services/retrieval_service.py` | Modified | Added `UpsertArticleTopic` and `upsert_article_topic` to imports; inside `_save_data_into_postgres()`, after article/claim writes, reads `topic_label` from `message.data.payload.topic_label` and calls `upsert_article_topic()` if present, wrapped in `try/except` to ensure topic failures never break the main transaction |

### Details
- **Upsert strategy**: Uses raw SQL `INSERT INTO article_topic ON CONFLICT (article_id) DO UPDATE` to handle re-processing of the same article without duplicate key errors.
- **Non-fatal design**: `upsert_article_topic` silently returns if the topic label doesn't resolve to a known `Topic` row — allows deployment before the topic table is fully seeded or when Stage 9 is disabled.
- **Payload contract**: Reads `topic_label` from `message.data.payload.topic_label`; absence of the key (Stage 9 skipped) is handled gracefully via the `if present` guard.
- **Transaction isolation**: The `try/except` wrapper around the topic upsert means a topic write failure rolls back only the topic write, not the article or claim rows committed in the same call.
- This is **Split 5** of a multi-split integration; Split 1 (this file) added the DB schema, ORM models, and seed data. Later splits are expected to add end-to-end tests and API query extensions.

### Pipeline Impact
**Retrieval stage** — moderate impact. The `_save_data_into_postgres()` write path now has an additional DB operation per message. NLP Stage 9 (topic classifier output) is the upstream dependency. API and scrape stages unaffected. E2E stability not yet verified for this split; non-fatal fallback minimises regression risk.

---
## [2026-04-16 15:13] Topic Classifier Integration — Split 1: DB Schema & ORM Models

**Date**: April 16, 2026 at 3:13 PM UTC
**Agent**: `claude-inline`
**Branch**: `newretrieval-fixes`
**Triggered By**: Begin topic classifier pipeline integration — Split 1 covers purely additive DB layer work (migration, ORM models, seed data)

### Summary
Adds the `topic` and `article_topic` database tables plus their ORM counterparts to support the upcoming topic classifier pipeline stage. All changes are purely additive — no existing tables, models, or code paths were touched. The retrieval service will auto-create the new tables on next restart via SQLAlchemy's `create_all()`, and the 9 seed topics are applied idempotently on every startup.

### Files Changed
| File Path | Change Type | Description |
|-----------|-------------|-------------|
| `microservices/db/migrations/002_add_topic_tables.sql` | Created | Raw SQL migration: creates `topic` and `article_topic` tables with FK constraints, UNIQUE guards, and 2 indexes; seeds 9 canonical topic rows; wrapped in `BEGIN/COMMIT` with `IF NOT EXISTS` guards throughout |
| `microservices/retrieval_layer/db/models.py` | Modified | Added `Topic` ORM model (id SERIAL PK, name String(100) unique, back-ref to ArticleTopic) and `ArticleTopic` ORM model (id SERIAL PK, article_id FK+unique, topic_id FK, confidence Float, relationship→Topic) |
| `microservices/retrieval_layer/db/session.py` | Modified | Extended `ensure_schema_compatibility()` to seed 9 topic rows via `INSERT … ON CONFLICT DO NOTHING` after existing article column backfills; table creation is handled by the pre-existing `Base.metadata.create_all(engine)` call |

### Details
- **Schema design**: `article_topic.article_id` carries a UNIQUE constraint — one topic per article (matches the classifier's single-label output). Confidence is stored as FLOAT for downstream ranking/filtering use.
- **Seed topics** (9 rows): Politics, World, Technology, Health, Science, Business, Entertainment, Sports, General — seeded `ON CONFLICT DO NOTHING` so re-runs are no-ops.
- **Indexes created**: `idx_article_topic_article_id`, `idx_article_topic_topic_id` — cover the expected retrieval query patterns.
- **Zero risk to existing data**: no `ALTER TABLE` statements on existing tables; migration is safe to run against a live DB.
- **Split strategy**: this is Split 1 of a multi-split integration. Future splits will add the classifier service consumer, the NLP pipeline writer, and the API retrieval query extensions.
- Related plan document: check `claude_docs/` for topic classifier integration plan if one exists.

### Pipeline Impact
**DB layer only** — no pipeline stages are live yet. Retrieval service restarts will auto-apply the schema. NLP and API stages unaffected until subsequent splits land. E2E stability not impacted by this split.

---
