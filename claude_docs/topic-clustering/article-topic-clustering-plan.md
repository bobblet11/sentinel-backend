# Article Topic Clustering — Comprehensive Analysis & Plan

## Problem Statement
The Sentinel Backend has no topic/category grouping for articles. Articles are stored with title, text, URL, outlet, author, and bias — but no mechanism to group them by topic (e.g., Politics, World, Technology, Health). The goal is to add topic-wise grouping **without rewriting existing schemas** — only adding new tables and endpoints.

---

## 1. Current State Audit

### Article Data Model
| Column | Type | Notes |
|--------|------|-------|
| id | SERIAL PK | |
| url | VARCHAR(250) | UNIQUE |
| title | VARCHAR(1024) | Nullable |
| text | TEXT | Full article text |
| html | TEXT | Raw HTML |
| publishedat | TIMESTAMP | |
| sentiment_id | FK → sentiment_analysis | Bias/sentiment scores |
| outlet_id | FK → news_outlet | Source outlet |
| author_id | FK → author | |

**No topic, category, or tag field exists.**

### Embeddings Landscape
| What | Dimension | Persisted? | Where |
|------|-----------|------------|-------|
| Claim embeddings | 768 (`all-mpnet-base-v2`) | Yes | `claim.decontextualised_embedding` (pgvector) |
| Sentence embeddings | 768 | No | Computed in NLP pipeline, passed in stream, not stored |
| Document embedding | 768 | No | `AnalysisResult.doc_embedding` exists in schema but never persisted |

### Key Infrastructure Already Available
- **pgvector** with HNSW cosine index — proven, production-ready
- **pg_trgm** for fuzzy text search
- **`all-mpnet-base-v2`** (768-dim) already loaded in NLP service
- **sentence-transformers** already installed
- **Ingestor cron job pattern** — template for periodic batch jobs

### What's Missing for Topic Grouping
- No article-level embeddings stored (only claim-level)
- No article listing/browse API (only single-job lookup by UUID)
- No topic tables, no classification logic

---

## 2. Method Evaluation

### Method A: Pure Clustering (K-Means / HDBSCAN on Embeddings)

**How it works**: Embed article titles/text -> reduce dimensionality (UMAP) -> cluster (K-Means or HDBSCAN) -> label clusters post-hoc.

| Criterion | Assessment |
|-----------|------------|
| **Accuracy** | Moderate. Clusters may not align with human-intuitive categories. K-Means requires pre-specifying K. HDBSCAN handles variable cluster sizes but produces noise points. |
| **Label Quality** | Poor without post-processing. Needs TF-IDF keyword extraction or manual labeling to name clusters. Labels like `cluster_0` are useless to users. |
| **Consistency** | Major weakness. Re-running clustering on updated data can reassign all articles to different clusters. Topic IDs are unstable across runs. |
| **Incremental Processing** | New articles can't be classified without re-clustering or a nearest-centroid heuristic. |
| **Scalability** | Good for batch. UMAP + HDBSCAN handles 100K+ documents. |
| **Compute** | UMAP is memory-intensive and needs the full dataset in memory. |
| **Verdict** | **Not recommended as primary method** — unstable labels, no strong incremental story, weak label quality. |

### Method B: BERTopic (UMAP + HDBSCAN + c-TF-IDF)

**How it works**: Uses transformer embeddings -> UMAP -> HDBSCAN -> c-TF-IDF for topic representation.

| Criterion | Assessment |
|-----------|------------|
| **Accuracy** | High topic coherence. Stronger than classical topic modeling for news-style corpora. |
| **Label Quality** | Good. c-TF-IDF generates keyword-based labels automatically. |
| **Consistency** | Moderate. `.transform()` can assign new docs to existing topics, but periodic refits can change topic definitions. |
| **Incremental Processing** | Good for assignment to existing topics. No new topic discovery without refit. |
| **Scalability** | Proven on large news datasets. Pre-computed embeddings help. |
| **Compute** | Needs `umap-learn` and `hdbscan`; moderate RAM cost. |
| **Can use existing embeddings** | Yes. |
| **Verdict** | **Strong contender** — very good for discovery, acceptable incremental support. |

### Method C: Zero-Shot BERTopic (Hybrid) — Recommended

**How it works**: Define target topics upfront (Politics, World, Technology, etc.). Articles matching those topics are assigned directly. Unmatched articles fall through to unsupervised clustering for discovery.

| Criterion | Assessment |
|-----------|------------|
| **Accuracy** | High. Predefined topics get more reliable assignment, while unknown topics can still be discovered. |
| **Label Quality** | Excellent. Predefined labels are human-readable by design. Discovered clusters get keyword labels. |
| **Consistency** | Strong. Predefined topics are stable anchors. |
| **Incremental Processing** | Good. `.transform()` works for assigning new articles to existing topics. |
| **Scalability** | Similar to BERTopic and suitable for large corpora with pre-computed embeddings. |
| **Compute** | Same dependency and RAM profile as BERTopic. |
| **Verdict** | **Best overall approach** — stable predefined labels plus discovery fallback. |

### Method D: Pure Zero-Shot Classification (BART-MNLI / DeBERTa-NLI)

**How it works**: Classify each article into predefined categories using NLI entailment.

| Criterion | Assessment |
|-----------|------------|
| **Accuracy** | Moderate. Roughly 72-78% on common news benchmarks without task-specific training. |
| **Label Quality** | Excellent — you define the labels directly. |
| **Consistency** | Deterministic per article. |
| **Incremental Processing** | Excellent. Each article is classified independently. |
| **Scalability** | Good. O(1) per article and no corpus-wide recomputation. |
| **Compute** | Requires another model and per-article inference cost. |
| **Discovery** | None. Only works for predefined categories. |
| **Verdict** | **Good fallback** — simpler and deterministic, but no discovery. |

### Method E: Mean Claim Embedding + Nearest Topic Centroid (SQL-Only)

**How it works**: Compute article embedding as `AVG(claim embeddings)` in SQL, then assign the nearest topic centroid.

| Criterion | Assessment |
|-----------|------------|
| **Accuracy** | Low to moderate. Claim embeddings capture semantics, but not always article topic cleanly. |
| **Label Quality** | Good if centroids are manually defined. |
| **Consistency** | Deterministic. |
| **Incremental Processing** | Excellent. |
| **Scalability** | Excellent — can be mostly SQL-driven. |
| **Compute** | Very cheap. |
| **Verdict** | **Cheap bootstrap option** but not the strongest quality-wise. |

---

## 3. Recommendation

### Primary Recommendation: Zero-Shot BERTopic

Why it fits this project best:

1. **Stable predefined categories** — `Politics`, `World`, `Technology`, `Health`, `Science`, `Business`, `Entertainment`, `Sports`
2. **Discovery of emerging topics** beyond the predefined set
3. **Leverages existing infrastructure** — the current embedding stack is already close to what is needed
4. **Incremental support** — new articles can be assigned without full retraining
5. **Purely additive** implementation path

### Fallback Recommendation: Pure Zero-Shot Classification

If BERTopic dependencies or operational complexity feel too heavy, pure zero-shot classification is the simpler fallback. It gives stable labels but sacrifices topic discovery.

---

## 4. Expected Project Impact

### Direct Product Benefits
- Topic browsing for articles
- Topic-filtered related article discovery
- Topic trend analysis over time
- Better fact-checking context
- Better analytics and reporting

### Benefits for Sentinel's Core Mission
- Topic-aware bias analysis
- Cross-source comparison within a topic
- Better visibility into misinformation hotspots by topic

### Overall Impact
**High value, low risk, additive feature.**

---

## 5. Implementation Plan

### Phase 1: Database Schema

Additive schema only:

```sql
CREATE TABLE IF NOT EXISTS topic_cluster (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    description TEXT,
    is_predefined BOOLEAN DEFAULT FALSE,
    keywords TEXT[],
    centroid VECTOR(768),
    article_count INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS article_topic (
    article_id INTEGER NOT NULL REFERENCES article(id) ON DELETE CASCADE,
    topic_id INTEGER NOT NULL REFERENCES topic_cluster(id) ON DELETE CASCADE,
    confidence FLOAT NOT NULL DEFAULT 0.0,
    assigned_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    method VARCHAR(50) DEFAULT 'bertopic',
    PRIMARY KEY (article_id, topic_id)
);

CREATE INDEX IF NOT EXISTS idx_article_topic_topic ON article_topic(topic_id);
CREATE INDEX IF NOT EXISTS idx_article_topic_article ON article_topic(article_id);

ALTER TABLE article ADD COLUMN IF NOT EXISTS doc_embedding VECTOR(768);
CREATE INDEX IF NOT EXISTS idx_article_doc_embedding_hnsw
ON article USING hnsw (doc_embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);
```

### Phase 2: Persist Article Embeddings

Persist `doc_embedding` end-to-end instead of dropping it after NLP.

Likely touch points:
- `microservices/nlp/components/embedder.py`
- `common/models/api/redis_models.py`
- `microservices/retrieval_layer/storage/crud.py`
- `microservices/retrieval_layer/db/models.py`

### Phase 3: Topic Clustering Script

Create a standalone script such as:

```text
scripts/topic_clustering.py
```

Core flow:
1. Load articles with `doc_embedding`
2. Run Zero-Shot BERTopic
3. Upsert into `topic_cluster` and `article_topic`
4. Use `.transform()` for incremental assignment of new articles

### Phase 4: API Endpoints

Suggested endpoints:

```text
GET /api/v1/topics
GET /api/v1/topics/{id}/articles
GET /api/v1/articles/{id}/topics
```

### Phase 5: Incremental Processing

Two options:
- Inline topic assignment in retrieval after article storage
- Periodic batch job

**Recommended first step**: periodic batch job, then move to inline if needed.

---

## 6. Dependencies and Risk

### New Python Packages

```text
bertopic>=0.16
umap-learn
hdbscan
```

### Affected Services
| Service | Change Type | Risk |
|---------|------------|------|
| `init.sql` | Add tables + column | Low |
| Retrieval Layer | Persist `doc_embedding` | Low to moderate |
| NLP Service | Ensure `doc_embedding` flows through | Low to moderate |
| API Service | Add endpoints | Low |
| New clustering script | New file only | Low |

### Risk Summary
- No Redis stream redesign needed
- No existing endpoint contract changes required
- No `ServiceTemplate` or pipeline ordering change required
- Blast radius is low if implemented additively

---

## 7. Migration Strategy

### Existing Articles
1. Compute `doc_embedding` for existing articles using `AVG(claim.decontextualised_embedding)` where necessary
2. Run the initial topic model over the existing corpus
3. Store topic assignments in the new tables

### New Articles
1. Persist `doc_embedding` during normal pipeline flow
2. Assign a topic through periodic batch processing or inline assignment
3. Periodically refit to discover emerging topics

### Consistency Strategy
- Predefined topics remain stable anchors
- Discovered topics can evolve on periodic refit
- Track assignment method in `article_topic.method`

---

## Proposed Execution Todo List

- [ ] Add `topic_cluster` and `article_topic` tables
- [ ] Add `doc_embedding` to `article`
- [ ] Persist `doc_embedding` in retrieval flow
- [ ] Ensure NLP payload carries `doc_embedding`
- [ ] Create clustering script with Zero-Shot BERTopic
- [ ] Backfill embeddings for existing articles
- [ ] Run initial topic assignment
- [ ] Add topic browsing API endpoints
- [ ] Add periodic re-clustering / assignment job
