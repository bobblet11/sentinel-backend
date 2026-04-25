# Topic Clustering POC Implementation Plan

## Scope

Standalone proof-of-concept scripts that run Zero-Shot BERTopic against existing data in the Sentinel PostgreSQL database. **No production code is modified.** No schema changes, no API endpoints, no pipeline modifications.

---

## 1. Codebase Audit Findings

### Database Schema (relevant tables)

**`article`** — `microservices/retrieval_layer/db/models.py:53-67`, `microservices/db/init.sql:47-53`
- `id` (SERIAL PK), `url`, `title`, `text`, `html`, `publishedat`, `sentiment_id`, `outlet_id`, `author_id`
- **No `doc_embedding` column exists.** The POC must compute document embeddings at runtime.

**`claim`** — `microservices/retrieval_layer/db/models.py:25-35`, `microservices/db/init.sql:143-155`
- `id`, `original_sentence`, `decontextualised_claim`, `decontextualised_embedding VECTOR(768)`, `centrality_score`, `article_id` (FK -> article)
- HNSW cosine index exists on `decontextualised_embedding`.

**`sentiment_analysis`** — bias/sentiment scores per article.

**`news_outlet`** — outlet name per article.

### Embedding Model

- Production model: `sentence-transformers/all-mpnet-base-v2` (768-dim)
- Configured in: `microservices/nlp/config.py:21`, `configs/.env.template:139`
- Embeddings stored as `VECTOR(768)` in `claim.decontextualised_embedding`
- The embedder (`microservices/nlp/components/embedder.py`) generates per-sentence embeddings; doc-level mean is described in docstring but **not persisted to DB**.

### DB Connection Pattern

- `microservices/retrieval_layer/db/session.py` — SQLAlchemy engine + `SessionLocal` factory
- Connection string built from env vars: `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_SSLMODE`
- `microservices/retrieval_layer/config.py` loads these via `common.env.get_env_var`
- `dotenv` is used (`load_dotenv()`) to pull from `.env` files

### Existing Script Patterns

- `scripts/database/inspect_aws.py` — loads `configs/aws/.env` via `load_dotenv(dotenv_path=...)`, then uses existing common modules
- Scripts use direct `load_dotenv` rather than the retrieval layer's config module
- The POC should follow this pattern: self-contained `.env` loading, direct SQLAlchemy session creation

### Key Constraint

The `claim.decontextualised_embedding` column uses pgvector `VECTOR(768)`. When fetched via SQLAlchemy + pgvector, values come back as Python lists/numpy arrays. The POC must handle this correctly.

---

## 2. File List with Exact Paths

### New files to create (all under `scripts/topic_clustering/`)

| File | Purpose |
|------|---------|
| `scripts/topic_clustering/__init__.py` | Package marker (empty) |
| `scripts/topic_clustering/requirements.txt` | Isolated deps for the POC |
| `scripts/topic_clustering/poc_cluster.py` | Main clustering script |
| `scripts/topic_clustering/test_quality.py` | Topic assignment quality validation |
| `scripts/topic_clustering/test_consistency.py` | Determinism / reproducibility test |
| `scripts/topic_clustering/test_edge_cases.py` | Edge case handling (no claims, single claim, etc.) |

No existing files are modified.

---

## 3. Per-File Specification

### 3.1 `scripts/topic_clustering/requirements.txt`

```
bertopic>=0.16
umap-learn>=0.5.5
hdbscan>=0.8.33
sentence-transformers>=2.2.0
psycopg2-binary>=2.9
sqlalchemy>=2.0
pgvector>=0.2.0
python-dotenv>=1.0
numpy>=1.24
pandas>=2.0
```

**Notes:**
- `sentence-transformers` is needed because BERTopic's zero-shot mode uses an embedding model to embed the candidate topic labels. The POC can re-use `all-mpnet-base-v2` for this.
- These deps are **not** added to any service `requirements.txt`. Install in an isolated venv.
- `psycopg2-binary` is the quick-start PostgreSQL adapter; production uses `psycopg2` but binary is fine for a POC script.

### 3.2 `scripts/topic_clustering/poc_cluster.py`

**What it does:**
1. Connects to PostgreSQL using env vars (same as retrieval layer)
2. Fetches all articles that have at least one claim with a non-null embedding
3. Computes a document-level embedding per article by averaging its claim embeddings
4. Runs Zero-Shot BERTopic with 8 predefined topics
5. Outputs results to `scripts/topic_clustering/output/results.json` and `results.csv`
6. Prints a quality summary to stdout

**Key functions:**

```python
def load_env() -> dict:
    """
    Load DB connection params from configs/.env or environment.
    Returns dict with keys: host, port, db, user, password, sslmode.
    Uses dotenv with path 'configs/.env' (relative to repo root).
    Falls back to environment variables if .env not found.
    """

def get_engine(db_config: dict) -> Engine:
    """
    Create SQLAlchemy engine from config dict.
    Connection string: postgresql://{user}:{password}@{host}:{port}/{db}?sslmode={sslmode}
    Uses pool_pre_ping=True for robustness.
    """

def fetch_articles_with_embeddings(engine: Engine) -> pd.DataFrame:
    """
    SQL query that JOINs article + claim, groups by article.id,
    and computes AVG(decontextualised_embedding) as the doc embedding.

    Raw SQL approach (pgvector avg works in SQL):
        SELECT a.id, a.title, a.url, a.text,
               AVG(c.decontextualised_embedding) as doc_embedding,
               COUNT(c.id) as claim_count
        FROM article a
        JOIN claim c ON c.article_id = a.id
        WHERE c.decontextualised_embedding IS NOT NULL
        GROUP BY a.id, a.title, a.url, a.text

    Returns DataFrame with columns: id, title, url, text, doc_embedding, claim_count.

    IMPORTANT: pgvector's AVG() on VECTOR columns returns a VECTOR.
    The pgvector SQLAlchemy adapter will deserialize this to a numpy array.
    If it comes back as a string like '[0.1, 0.2, ...]', parse it.
    """

def run_zero_shot_bertopic(
    docs: List[str],
    embeddings: np.ndarray,
    predefined_topics: List[str],
    min_topic_size: int = 5,
    seed: int = 42,
) -> Tuple[BERTopic, List[int], List[float]]:
    """
    Configure and run Zero-Shot BERTopic.

    predefined_topics = [
        "Politics", "World", "Technology", "Health",
        "Science", "Business", "Entertainment", "Sports"
    ]

    BERTopic config:
    - embedding_model: 'sentence-transformers/all-mpnet-base-v2'
      (used to embed the topic label strings for zero-shot matching)
    - umap_model: UMAP(n_components=5, n_neighbors=15, min_dist=0.0,
                        metric='cosine', random_state=seed)
    - hdbscan_model: HDBSCAN(min_cluster_size=min_topic_size,
                              min_samples=3, metric='euclidean',
                              prediction_data=True)
    - zeroshot_topic_list: predefined_topics
    - zeroshot_min_similarity: 0.5  (articles below this go to unsupervised)
    - nr_topics: None (let BERTopic decide for unsupervised portion)

    docs: article titles (or title + first 200 chars of text) — short text
          works better for topic assignment than full article text.
    embeddings: precomputed 768-dim doc embeddings from claim averaging.

    Returns (model, topics_per_doc, probabilities_per_doc).
    """

def build_results(
    df: pd.DataFrame,
    topics: List[int],
    probs: List[float],
    topic_model: BERTopic,
) -> List[dict]:
    """
    Merge topic assignments back with article metadata.
    Each result dict:
    {
        "article_id": int,
        "title": str,
        "url": str,
        "claim_count": int,
        "topic_id": int,
        "topic_label": str,
        "confidence": float,
        "is_predefined": bool
    }
    """

def print_quality_summary(results: List[dict], topic_model: BERTopic) -> None:
    """
    Print to stdout:
    - Total articles processed
    - Articles per topic (count + percentage)
    - Articles assigned to predefined vs discovered topics
    - Articles in outlier topic (-1)
    - Mean/median/min/max confidence across all assignments
    - Top 5 keywords per discovered topic (from c-TF-IDF)
    """

def save_results(results: List[dict], output_dir: str) -> None:
    """
    Save to:
    - {output_dir}/results.json  (full results list)
    - {output_dir}/results.csv   (flattened for easy inspection)
    - {output_dir}/topic_info.json (BERTopic topic_model.get_topic_info())
    Creates output_dir if it doesn't exist.
    """

def main():
    """
    Entry point. Orchestrates:
    1. load_env()
    2. get_engine()
    3. fetch_articles_with_embeddings()
    4. Validate: exit early if < 10 articles with embeddings
    5. run_zero_shot_bertopic()
    6. build_results()
    7. print_quality_summary()
    8. save_results()

    CLI args (argparse):
    --env-file    Path to .env file (default: configs/.env)
    --output-dir  Output directory (default: scripts/topic_clustering/output)
    --min-topic-size  Minimum cluster size for HDBSCAN (default: 5)
    --seed        Random seed for reproducibility (default: 42)
    --zeroshot-threshold  Min cosine similarity for zero-shot match (default: 0.5)
    --use-title-only  If set, use only title for BERTopic doc input (default: title + first 200 chars)
    """
```

**Critical implementation details:**

1. **pgvector AVG() behavior**: The SQL `AVG(c.decontextualised_embedding)` works natively with pgvector and returns a VECTOR. However, when fetched via raw SQL + `engine.execute()`, the result may come as a string representation. The script must handle both cases (numpy array from ORM, or string parse from raw SQL). Use `text()` queries with explicit type casting if needed:
   ```sql
   AVG(c.decontextualised_embedding)::vector(768) as doc_embedding
   ```

2. **Doc text for BERTopic**: BERTopic needs text documents even when pre-computed embeddings are provided (for c-TF-IDF topic representation). Use `title + first_200_chars_of_text` as the doc string. If title is NULL, use first 200 chars of text only.

3. **Embedding dimension check**: Assert that all doc embeddings have exactly 768 dimensions before passing to BERTopic. Log and skip any articles where averaging produced a different dimension (should not happen, but defensive).

4. **Memory**: For a corpus of ~10K articles, the 768-dim embedding matrix is ~30MB. UMAP will need ~2-4x that. Total RAM for the POC should stay under 2GB.

5. **BERTopic zero-shot flow**: When `zeroshot_topic_list` is provided, BERTopic first tries to match each document to one of the predefined topics using cosine similarity of the document embedding against the embedded topic labels. Documents below `zeroshot_min_similarity` fall through to standard UMAP+HDBSCAN clustering.

### 3.3 `scripts/topic_clustering/test_quality.py`

**What it validates:**
1. **Confidence distribution** — histogram of confidence scores; flag if >50% of articles have confidence < 0.3
2. **Topic coverage** — verify all 8 predefined topics have at least 1 article assigned (warn if any are empty)
3. **Outlier ratio** — percentage of articles assigned to topic -1 (outliers); flag if > 30%
4. **Discovered topics sanity** — if BERTopic finds extra topics beyond the 8 predefined, print their keywords and sample articles for manual inspection
5. **Title-topic coherence spot check** — for each predefined topic, print 5 sample article titles so the operator can eyeball relevance

**How to run:**
```bash
cd /path/to/sentinel-backend
python -m scripts.topic_clustering.test_quality --results-file scripts/topic_clustering/output/results.json --topic-info-file scripts/topic_clustering/output/topic_info.json
```

**Key functions:**
```python
def load_results(results_path: str) -> List[dict]
def check_confidence_distribution(results: List[dict]) -> dict  # returns stats + pass/fail
def check_topic_coverage(results: List[dict], predefined: List[str]) -> dict
def check_outlier_ratio(results: List[dict]) -> dict
def check_discovered_topics(topic_info_path: str, results: List[dict]) -> dict
def spot_check_titles(results: List[dict], n_samples: int = 5) -> None  # prints to stdout
def main()  # runs all checks, prints report, exits 0 if all pass, 1 if any fail
```

### 3.4 `scripts/topic_clustering/test_consistency.py`

**What it validates:**
1. **Determinism** — run clustering twice with the same seed on the same data, verify identical topic assignments
2. **Near-determinism with different seeds** — run with 2 different seeds, measure agreement (should be >80% for predefined topics since zero-shot matching is mostly deterministic; UMAP/HDBSCAN portion may vary)

**How to run:**
```bash
cd /path/to/sentinel-backend
python -m scripts.topic_clustering.test_consistency --env-file configs/.env
```

**Key functions:**
```python
def run_clustering_twice(engine, seed: int) -> Tuple[List[int], List[int]]
def compute_agreement(topics_a: List[int], topics_b: List[int]) -> float  # % matching
def main()  # runs both checks, prints report
```

**Implementation note:** This test actually connects to the DB and runs the full pipeline twice. It imports functions from `poc_cluster.py` to avoid duplication. The UMAP random_state and numpy seed must both be fixed for determinism.

### 3.5 `scripts/topic_clustering/test_edge_cases.py`

**What it validates:**
1. **Articles with no claims** — query articles with zero claims; confirm they are excluded from clustering (not passed to BERTopic)
2. **Articles with single claim** — these articles' doc embedding equals their sole claim embedding; verify they still get a valid topic assignment
3. **Articles with claims but all null embeddings** — should be excluded gracefully
4. **Empty corpus** — if fetch returns 0 articles with embeddings, script should exit with a clear message, not crash
5. **Very short title/text** — articles where title is NULL and text is < 10 chars; verify BERTopic handles the short doc string

**How to run:**
```bash
cd /path/to/sentinel-backend
python -m scripts.topic_clustering.test_edge_cases --env-file configs/.env
```

**Key functions:**
```python
def test_no_claims_excluded(engine) -> bool
def test_single_claim_articles(engine, topic_model, embeddings, topics) -> bool
def test_null_embeddings_excluded(engine) -> bool
def test_empty_corpus_handling() -> bool  # uses mock/empty DataFrame
def test_short_text_handling(engine, topic_model) -> bool
def main()
```

**Implementation note:** Some tests query the DB to count edge cases. Others mock data to test the clustering functions in isolation. Import `fetch_articles_with_embeddings` and `run_zero_shot_bertopic` from `poc_cluster.py`.

---

## 4. Dependencies and Install Instructions

### Prerequisites
- Python 3.11+ (matching the project's Docker base images)
- Access to the Sentinel PostgreSQL database (either local or via SSH tunnel to AWS RDS)
- The database must have articles with claims that have non-null `decontextualised_embedding` values

### Installation

```bash
# From repo root
cd scripts/topic_clustering

# Create isolated virtual environment (do NOT install into the project's main venv)
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# Install POC dependencies
pip install -r requirements.txt

# Verify BERTopic import
python -c "from bertopic import BERTopic; print('BERTopic OK')"
```

### Environment Setup

The script reads DB connection from a `.env` file. Either:
1. Use the existing `configs/.env` (if it exists and has Postgres credentials), or
2. Create a minimal `scripts/topic_clustering/.env` with:

```env
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=sentinel
POSTGRES_USER=sentinel
POSTGRES_PASSWORD=sentinelpass
POSTGRES_SSLMODE=disable
```

For AWS RDS via tunnel:
```env
POSTGRES_HOST=localhost
POSTGRES_PORT=15433
POSTGRES_DB=postgres
POSTGRES_USER=postgres
POSTGRES_PASSWORD=<rds-password>
POSTGRES_SSLMODE=require
```

### Running

```bash
# From repo root, with the POC venv activated

# 1. Run clustering
python -m scripts.topic_clustering.poc_cluster --env-file configs/.env

# 2. Validate quality
python -m scripts.topic_clustering.test_quality \
  --results-file scripts/topic_clustering/output/results.json \
  --topic-info-file scripts/topic_clustering/output/topic_info.json

# 3. Test consistency
python -m scripts.topic_clustering.test_consistency --env-file configs/.env

# 4. Test edge cases
python -m scripts.topic_clustering.test_edge_cases --env-file configs/.env
```

---

## 5. Risk Assessment

### No-Regression Risks (Production Impact)

| Risk | Severity | Likelihood | Mitigation |
|------|----------|------------|------------|
| POC accidentally writes to DB | Critical | Unlikely | Script uses **read-only queries only**. No INSERT/UPDATE/DELETE. Enforce by using `engine.connect()` without commit, or by connecting with a read-only DB user. Add assertion at top of script. |
| POC imports modify retrieval layer module state | Medium | Unlikely | POC does NOT import from `microservices.retrieval_layer`. It builds its own engine/session. |
| Heavy SELECT query locks DB during pipeline processing | Low | Possible | The AVG+GROUP BY query is a single read. On a table with HNSW index, this won't block writes. For extra safety, run during low-traffic periods. |
| BERTopic deps conflict with project deps | None | N/A | POC uses isolated venv. No shared dependency state. |

### POC-Specific Risks

| Risk | Severity | Likelihood | Mitigation |
|------|----------|------------|------------|
| pgvector AVG() returns unexpected format | Medium | Possible | Test with a small query first (`LIMIT 5`). Add explicit type parsing with fallback. |
| Too few articles in DB for meaningful clustering | High | Possible | Script checks article count before running. Exits with message if < 10. BERTopic's HDBSCAN needs a minimum cluster size. |
| UMAP fails on small datasets (< 15 articles) | High | Possible | Set `n_neighbors=min(15, n_articles - 1)` dynamically. |
| Zero-shot topic embedding model download on first run | Low | Certain | BERTopic will download `all-mpnet-base-v2` on first run if not cached. Document this. ~400MB download. |
| claim embeddings are all-zeros or degenerate | Medium | Unlikely | Add a sanity check: compute mean norm of embeddings, warn if < 0.1. |

### Constraints and Assumptions

1. **Assumes claim embeddings exist**: The POC is only useful if the DB has articles with non-null `decontextualised_embedding` on their claims. If the pipeline has been running, this should be the case.
2. **768-dim assumption**: Both the stored claim embeddings and the BERTopic embedding model must use 768 dimensions. The production model is `all-mpnet-base-v2` (768-dim). The POC must use the same model for zero-shot label embedding to ensure cosine similarity is meaningful.
3. **No GPU required**: BERTopic's UMAP+HDBSCAN runs on CPU. The sentence-transformers model for embedding the 8 topic labels is trivial (8 short strings). CPU is sufficient.
4. **Read-only**: The POC must not write to any database table. All output goes to local files.

---

## 6. Dependency Graph

```
poc_cluster.py
  ├── reads: article table (id, title, text, url)
  ├── reads: claim table (decontextualised_embedding, article_id)
  ├── computes: AVG(claim embeddings) -> doc_embedding per article
  ├── runs: BERTopic zero-shot clustering
  ├── writes: output/results.json, output/results.csv, output/topic_info.json
  │
  └── NO dependency on any microservices/* or common/* module
      (builds its own DB connection from env vars + SQLAlchemy + pgvector)

test_quality.py
  └── reads: output/results.json, output/topic_info.json

test_consistency.py
  ├── imports: poc_cluster.fetch_articles_with_embeddings
  ├── imports: poc_cluster.run_zero_shot_bertopic
  └── reads: DB (same as poc_cluster.py)

test_edge_cases.py
  ├── imports: poc_cluster.fetch_articles_with_embeddings
  ├── imports: poc_cluster.run_zero_shot_bertopic
  └── reads: DB (same as poc_cluster.py)
```

---

## 7. Predefined Topics

These 8 topics align with the plan in `claude_docs/topic-clustering/article-topic-clustering-plan.md`:

```python
PREDEFINED_TOPICS = [
    "Politics",
    "World",
    "Technology",
    "Health",
    "Science",
    "Business",
    "Entertainment",
    "Sports",
]
```

BERTopic will embed these strings using `all-mpnet-base-v2` and compute cosine similarity against each article's doc embedding. Articles with similarity >= `zeroshot_min_similarity` (default 0.5) get assigned to the best-matching predefined topic. The rest fall through to unsupervised HDBSCAN clustering.

---

## 8. SQL Query for Document Embeddings

The core query that powers the POC:

```sql
SELECT
    a.id,
    a.title,
    a.url,
    LEFT(a.text, 500) as text_snippet,
    AVG(c.decontextualised_embedding)::vector(768) as doc_embedding,
    COUNT(c.id) as claim_count
FROM article a
JOIN claim c ON c.article_id = a.id
WHERE c.decontextualised_embedding IS NOT NULL
GROUP BY a.id, a.title, a.url, a.text
HAVING COUNT(c.id) > 0;
```

**Why `LEFT(a.text, 500)`**: We only need a text snippet for BERTopic's c-TF-IDF representation. Pulling full article text for thousands of articles wastes memory. 500 chars is sufficient for keyword extraction.

**Why `AVG()` works**: pgvector supports element-wise `AVG()` on `VECTOR` columns in `GROUP BY` queries. This computes the centroid of all claim embeddings for each article — a reasonable document-level representation.

---

## 9. Output Format

### results.json
```json
[
  {
    "article_id": 42,
    "title": "Senate Passes New Climate Bill",
    "url": "https://example.com/article/42",
    "claim_count": 5,
    "topic_id": 0,
    "topic_label": "Politics",
    "confidence": 0.78,
    "is_predefined": true
  }
]
```

### results.csv
Same fields, flattened. One row per article.

### topic_info.json
BERTopic's `get_topic_info()` DataFrame serialized to JSON. Contains topic ID, count, name, and representative keywords.

---

## 10. Quality Summary Output (stdout)

```
============================================
  TOPIC CLUSTERING POC — QUALITY SUMMARY
============================================

Total articles processed: 847
Articles with embeddings: 812
Articles excluded (no claims/embeddings): 35

--- Topic Distribution ---
  Politics        : 156 (19.2%)
  World           :  98 (12.1%)
  Technology      : 112 (13.8%)
  Health          :  89 (11.0%)
  Science         :  45 ( 5.5%)
  Business        : 134 (16.5%)
  Entertainment   :  67 ( 8.3%)
  Sports          :  42 ( 5.2%)
  [Discovered: Climate Change] : 23 ( 2.8%)
  [Outlier / -1]  :  46 ( 5.7%)

--- Confidence Stats ---
  Mean  : 0.62
  Median: 0.67
  Min   : 0.12
  Max   : 0.94

--- Predefined vs Discovered ---
  Predefined topics: 743 articles (91.5%)
  Discovered topics:  23 articles ( 2.8%)
  Outliers:           46 articles ( 5.7%)

============================================
```

---

## 11. Execution Checklist for Implementer

1. [ ] Create `scripts/topic_clustering/` directory
2. [ ] Create `__init__.py` (empty)
3. [ ] Create `requirements.txt` per spec in section 3.1
4. [ ] Implement `poc_cluster.py` per spec in section 3.2
5. [ ] Implement `test_quality.py` per spec in section 3.3
6. [ ] Implement `test_consistency.py` per spec in section 3.4
7. [ ] Implement `test_edge_cases.py` per spec in section 3.5
8. [ ] Test: create venv, install deps, run `poc_cluster.py` against DB
9. [ ] Test: run all three test scripts
10. [ ] Verify: no imports from `microservices/` or `common/` in any POC file
11. [ ] Verify: no INSERT/UPDATE/DELETE statements in any POC file
12. [ ] Verify: output files are created in `scripts/topic_clustering/output/`
