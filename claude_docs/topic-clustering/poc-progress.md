# Topic Clustering POC — Progress & Steps Remaining

_Last updated: 2026-04-16_

---

## What We Are Building

Zero-Shot BERTopic topic clustering for Sentinel articles.  
Each article is assigned to one of 8 predefined topic categories:
**Politics, World, Technology, Health, Science, Business, Entertainment, Sports**  
with HDBSCAN fallback for articles that don't match any predefined topic with sufficient confidence.

Method: **Method C** from `article-topic-clustering-plan.md`.

---

## Files Created

| File | Purpose |
|---|---|
| `scripts/topic_clustering/__init__.py` | Package marker |
| `scripts/topic_clustering/requirements.txt` | Isolated venv deps (bertopic, umap-learn, hdbscan, etc.) |
| `scripts/topic_clustering/poc_cluster.py` | Main POC script — fetches articles, runs BERTopic, saves results |
| `scripts/topic_clustering/test_quality.py` | Validates output: confidence distribution, topic coverage, outlier ratio, spot-check titles |
| `scripts/topic_clustering/test_consistency.py` | Determinism checks: same-seed 100% agreement, cross-seed ≥80% agreement |
| `scripts/topic_clustering/test_edge_cases.py` | Edge case checks: null titles excluded, long title truncation, empty corpus early exit, live DB fetch |
| `configs/local/.env` | Local Docker postgres credentials for running scripts outside Docker |

---

## Current Document Strategy

Each article document passed to BERTopic is:

```
{article title} + {top 2 claims by centrality_score}
```

- Title alone is ambiguous for generic headlines ("New Study Reveals…", "Markets Hit Record High")
- Top 2 claims by `centrality_score` add disambiguating factual content
- No pre-computed embeddings fetched — BERTopic embeds documents internally using `sentence-transformers/all-mpnet-base-v2`
- Articles without any claims fall back to title only

SQL used:
```sql
SELECT a.id, a.title, a.url, top_c.top_claims
FROM article a
LEFT JOIN LATERAL (
    SELECT STRING_AGG(decontextualised_claim, ' ') AS top_claims
    FROM (
        SELECT decontextualised_claim
        FROM claim
        WHERE article_id = a.id
          AND decontextualised_claim IS NOT NULL
        ORDER BY centrality_score DESC NULLS LAST
        LIMIT 2
    ) sub
) top_c ON true
WHERE a.title IS NOT NULL AND a.title != ''
ORDER BY a.id
```

---

## Local Test Setup

A local PostgreSQL container with pgvector was started from the pgAdmin backup:

```bash
# Container (already running)
docker run -d --name sentinel-pg-local \
  -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=sentinelpass \
  -e POSTGRES_DB=postgres -p 15432:5432 \
  pgvector/pgvector:pg17

# Restore backup
docker exec sentinel-pg-local pg_restore -U postgres -d postgres --no-owner /backup.sql
```

Backup file: `scripts/topic_clustering/backup.sql` (gitignored, 555 MB)

DB stats: **4,268 articles**, **26,255 claims** (26,225 with non-null embeddings)

Credentials: `configs/local/.env` (gitignored)

---

## How to Run

From the repo root, with the Docker container running:

```bash
# Main clustering run (saves results to scripts/topic_clustering/output/)
scripts/topic_clustering/.venv/bin/python -m scripts.topic_clustering.poc_cluster \
  --env-file configs/local/.env

# Quality checks (run after poc_cluster)
scripts/topic_clustering/.venv/bin/python -m scripts.topic_clustering.test_quality

# Determinism checks
scripts/topic_clustering/.venv/bin/python -m scripts.topic_clustering.test_consistency \
  --env-file configs/local/.env

# Edge case checks
scripts/topic_clustering/.venv/bin/python -m scripts.topic_clustering.test_edge_cases \
  --env-file configs/local/.env
```

Venv setup (first time only):
```bash
cd scripts/topic_clustering
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cd ../..
```

---

## Progress

### Completed

- [x] Reviewed and understood `article-topic-clustering-plan.md`
- [x] Audited DB schema — confirmed `claim.decontextualised_claim`, `claim.centrality_score`, `claim.decontextualised_embedding VECTOR(768)` exist
- [x] Created isolated venv and `requirements.txt` (no changes to service requirements)
- [x] Implemented `poc_cluster.py` — full pipeline: DB fetch → BERTopic → results CSV/JSON
- [x] Implemented `test_quality.py` — confidence, coverage, outlier ratio, spot-check titles
- [x] Implemented `test_consistency.py` — same-seed determinism, cross-seed agreement
- [x] Implemented `test_edge_cases.py` — null titles, long titles, empty corpus, live DB
- [x] Resolved DB connectivity issue (WSL cannot reach `host.docker.internal`; use local Docker container instead)
- [x] Set up local Docker postgres container with pgvector and restored DB backup
- [x] Switched document strategy from pre-computed claim embeddings → title + top 2 claims (simpler, no vector math, better semantics)

### Not Yet Done

- [ ] **Actually run the POC** — `poc_cluster.py` has not been executed successfully yet; results not yet generated
- [ ] **Run test_quality.py** — depends on POC output (`results.json`, `topic_info.json`)
- [ ] **Run test_consistency.py** — needs live DB and ~10 min per run (BERTopic is slow on CPU)
- [ ] **Run test_edge_cases.py** — needs live DB
- [ ] **Review results** — inspect `output/results.json`, check spot-check titles, evaluate whether 8 predefined topics are sufficient or need tuning
- [ ] **Tune hyperparameters if needed** — `--zeroshot-threshold` (default 0.5), `--min-topic-size` (default 5)
- [ ] **Decide on production path** — once POC validates, plan integration into the pipeline (API endpoint, DB column, or separate job)

---

## Known Issues / Gotchas

- **WSL ↔ Docker networking**: `host.docker.internal` only resolves inside Docker containers, not from WSL directly. Always use `localhost` with the exposed port when running scripts from WSL.
- **BERTopic is slow on CPU**: First run will download `all-mpnet-base-v2` (~420 MB) and may take several minutes to fit on 4,268 articles. Subsequent runs reuse the cached model.
- **Container persistence**: The `sentinel-pg-local` Docker container must be running before executing any script. Check with `docker ps`. If stopped, restart with `docker start sentinel-pg-local`.
- **backup.sql is gitignored**: The DB backup file is not committed. If the container is lost, re-download from pgAdmin or AWS RDS.
