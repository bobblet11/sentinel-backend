---
## [2026-04-16 00:00] Topic Clustering POC — Zero-Shot BERTopic (Method C)

**Date**: April 16, 2026 at 12:00 AM UTC
**Agent**: `plan-executor` (via `systems-planner` planning phase)
**Branch**: `features/cluster`
**Triggered By**: Validate Zero-Shot BERTopic as the implementation approach for article topic clustering before committing to DB schema changes, new API endpoints, or service-level infrastructure.

### Summary
Created a fully standalone proof-of-concept under `scripts/topic_clustering/` that runs Zero-Shot BERTopic against existing claim embeddings in PostgreSQL. The POC validates Method C from the topic clustering plan with three test suites covering output quality, cross-seed consistency, and edge-case robustness. No production code was modified.

### Files Changed
| File Path | Change Type | Description |
|-----------|-------------|-------------|
| `scripts/topic_clustering/__init__.py` | Created | Empty package marker for the POC directory |
| `scripts/topic_clustering/requirements.txt` | Created | Isolated dependency list: bertopic, umap-learn, hdbscan, sentence-transformers, psycopg2-binary, sqlalchemy, pgvector, python-dotenv, numpy, pandas |
| `scripts/topic_clustering/poc_cluster.py` | Created | Main clustering script: connects to PostgreSQL, fetches articles with claim embeddings via SQL `AVG()`, runs Zero-Shot BERTopic with 8 predefined topic labels, writes `results.json`, `results.csv`, `topic_info.json` |
| `scripts/topic_clustering/test_quality.py` | Created | Validates confidence distribution, topic coverage, outlier ratio, discovered topics, and spot-checks sample titles per topic |
| `scripts/topic_clustering/test_consistency.py` | Created | Tests same-seed determinism (100% expected) and cross-seed label agreement (>80% guideline) |
| `scripts/topic_clustering/test_edge_cases.py` | Created | Tests no-claim exclusion, single-claim inclusion, null embedding exclusion, empty corpus early exit (mocked), and short text handling |

### Details
- The POC is read-only against the live database — it fetches existing `claim_embeddings` and `articles` rows, runs BERTopic in memory, and writes output files locally. No DB writes.
- The 8 predefined topic seeds are: Politics, World, Technology, Health, Science, Business, Entertainment, Sports — derived from the plan document at `claude_docs/systems-planner/`.
- `poc_cluster.py` uses SQL `AVG()` to aggregate per-article claim embeddings into a single article-level vector before passing to BERTopic, avoiding the need for any new DB columns at this stage.
- The requirements.txt is intentionally isolated and not merged into any service's existing dependency tree; the POC must be installed in a separate venv.
- Next step after POC validation: promote to a scheduled background service with a new `article_topics` table and a `/api/v1/topics` endpoint, as outlined in the topic clustering plan.
- Related plan document: `claude_docs/systems-planner/` (see `add-article-topic-clustering-plan.md` journal entry for the planning phase record).

### Pipeline Impact
None. No microservice code, Pydantic schemas, Redis stream definitions, DB models, or API routes were modified. The POC is entirely outside the `microservices/`, `common/`, `tests/`, and `configs/` trees. E2E pipeline stability is unaffected.

---
