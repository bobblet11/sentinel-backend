# Sentinel Backend — Interface & Schema Registry

**Last Updated:** 2026-03-26T06:19:35Z

This document catalogs all inter-service message schemas, API DTOs, and database models to enable safe refactoring and schema evolution.

## Redis Stream Message Types

### 1. Article (Job Submission)
**Streams:** `user:to.be.scraped`, `background:to.be.scraped`  
**Producer:** API Service (user), Ingestor (background)  
**Consumer:** Web Scraper

```python
class Article(BaseModel):
    id: str                    # UUID
    job_id: str                # Reference to parent job
    url: str                   # Article URL
    title: Optional[str]       # Article title
    published_date: Optional[datetime]
    job_type: JobType          # USER or BACKGROUND
    retry_count: int = 0
    created_at: datetime
```

**Location:** `common/models/api/redis_models.py`

---

### 2. ScrapedArticle
**Streams:** `user:to.be.nlp`, `background:to.be.nlp`  
**Producer:** Web Scraper  
**Consumer:** NLP Service

```python
class ScrapedArticle(BaseModel):
    id: str                    # UUID (from Article)
    job_id: str                # Reference to parent job
    url: str
    title: str
    body: str                  # Scraped content
    summary: Optional[str]
    job_type: JobType          # USER or BACKGROUND
    retry_count: int = 0
    created_at: datetime
    processed_at: datetime     # When scraped
```

**Location:** `common/models/api/redis_models.py`

---

### 3. NLPResult
**Streams:** `user:to.be.retrieval`, `background:to.be.retrieval`  
**Producer:** NLP Service  
**Consumer:** Retrieval Layer

```python
class NLPResult(BaseModel):
    id: str                    # UUID (from Article)
    job_id: str                # Reference to parent job
    url: str
    title: str
    body: str
    job_type: JobType          # USER or BACKGROUND
    
    # NLP Pipeline Outputs
    claims_in_article: List[Claim]          # Extracted claims
    entities_in_article: List[Entity]       # Named entities
    bias_profile: BiasProfile               # Bias & sentiment analysis
    doc_embedding: List[float]              # Document-level embedding (384-dim)
    
    processed_at: datetime
```

**Location:** `common/models/api/redis_models.py`

---

### 4. Claim
**Container:** NLPResult.claims_in_article  
**Producer:** NLP BiasDetector + CheckWorthinessFilter  
**Consumer:** Retrieval Layer (storage + semantic search)

```python
class Claim(BaseModel):
    confidence: float                      # 0.0–1.0
    source_sentence_indices: List[int]     # Position in sentences array
    decontextualised_claim_text: str       # Extracted claim
    decontextualised_claim_embedding: List[float]  # Claim-level embedding (384-dim)
    NER_entities: List[Entity]             # Referenced entities
```

**Location:** `common/models/api/redis_models.py`

---

### 5. Entity
**Container:** NLPResult.entities_in_article  
**Producer:** NLP EntityRecognizer  
**Consumer:** Retrieval Layer (storage)

```python
class Entity(BaseModel):
    entity_text: str           # The entity string
    type_of_entity: str        # NER label (PERSON, ORG, LOC, etc.)
    start_char: int            # Character offset in body
    end_char: int              # Character offset in body
```

**Location:** `common/models/api/redis_models.py`

---

### 6. BiasProfile
**Container:** NLPResult.bias_profile  
**Producer:** NLP BiasDetector  
**Consumer:** Retrieval Layer (storage + API response)

```python
class BiasProfile(BaseModel):
    bias_category: str         # Category label (e.g., "left", "right", "neutral")
    bias_score: float          # 0.0–1.0 confidence
    bias_analysis_confidence: float  # Model confidence
    sentiment_category: str    # "positive", "negative", "neutral"
    sentiment_analysis_confidence: float  # 0.0–1.0
```

**Location:** `common/models/api/redis_models.py`

---

## API Endpoints & Request/Response DTOs

### POST /api/v1/jobs
**Purpose:** Submit an article for processing  
**Request DTO:**

```python
class JobCreate(BaseModel):
    url: str                   # Article URL (required)
    job_type: JobType          # USER or BACKGROUND (default: USER)
```

**Response DTO:**

```python
class JobResponse(BaseModel):
    id: str                    # Job UUID
    url: str
    job_type: JobType
    status: JobStatus          # QUEUED, PROCESSING, COMPLETED, FAILED
    created_at: datetime
    completed_at: Optional[datetime]
```

**Location:** `common/models/api/dtos/job.py`, `microservices/api/app/api/v1/endpoints/jobs.py`

---

### GET /api/v1/jobs/{job_id}/result
**Purpose:** Retrieve completed job result  
**Response DTO:**

```python
class JobResult(BaseModel):
    job_id: str
    url: str
    title: str
    body: str
    claims: List[Claim]        # Extracted claims
    entities: List[Entity]     # Named entities
    bias_profile: BiasProfile  # Bias & sentiment
    doc_embedding: List[float] # 384-dim document embedding
    status: JobStatus
    completed_at: datetime
```

**Location:** `microservices/api/app/api/v1/endpoints/jobs.py`

---

## Database Models (PostgreSQL + pgvector)

### articles Table
```sql
CREATE TABLE articles (
    id UUID PRIMARY KEY,
    job_id UUID FOREIGN KEY,
    url TEXT NOT NULL UNIQUE,
    title TEXT,
    body TEXT,
    summary TEXT,
    published_date TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    INDEX(url)
);
```

**SQLAlchemy Model:** `common/models/database/db_models.py::Article`

---

### jobs Table
```sql
CREATE TABLE jobs (
    id UUID PRIMARY KEY,
    url TEXT NOT NULL,
    job_type ENUM('USER', 'BACKGROUND'),
    status ENUM('QUEUED', 'PROCESSING', 'COMPLETED', 'FAILED'),
    created_at TIMESTAMP DEFAULT NOW(),
    processing_started_at TIMESTAMP,
    completed_at TIMESTAMP,
    INDEX(status),
    INDEX(job_type)
);
```

**SQLAlchemy Model:** `common/models/database/db_models.py::Job`

---

### results Table
```sql
CREATE TABLE results (
    id UUID PRIMARY KEY,
    job_id UUID FOREIGN KEY,
    claims JSONB,              -- Serialized List[Claim]
    entities JSONB,            -- Serialized List[Entity]
    bias_profile JSONB,        -- Serialized BiasProfile
    doc_embedding vector(384), -- pgvector for semantic search
    created_at TIMESTAMP DEFAULT NOW(),
    INDEX(doc_embedding) -- HNSW index for fast search
);
```

**SQLAlchemy Model:** `common/models/database/db_models.py::Result`

---

## Redis Hash Store

**Namespace:** `retrieval:hash.store`  
**Usage:** Final job results are stored in a Redis hash for fast retrieval

**Key Format:** `retrieval:hash.store:{job_id}`  
**Value:** Serialized `NLPResult` (JSON)

```python
hash_store.set(
    f"retrieval:hash.store:{job_id}",
    json.dumps(nlp_result.dict())
)
```

**Location:** `common/redis_client/hash_store.py`

---

## Inter-Service Contracts & Invariants

### Invariant 1: Message Immutability
- Once a message is published to a stream, **it must not be mutated by downstream services**
- Downstream services may add fields to their own internal messages, but must preserve upstream fields
- **Example:** NLP receives `ScrapedArticle`, adds `nlp_results`, publishes as `NLPResult`

### Invariant 2: Stream Ordering
- **Within a single job:** Messages flow sequentially (scrape → NLP → retrieval)
- **Priority handling:** User jobs (`user:*`) are processed before background jobs (`background:*`)
- **No guarantee:** Messages from different jobs may be interleaved

### Invariant 3: Failure Isolation
- **Transient failures:** Retry via failure stream (automatic or manual)
- **Permanent failures:** Message logged and moved to `failure:*` stream for human review
- **No data loss:** All messages (success or failure) are persisted to streams

### Invariant 4: Embedding Consistency
- **Embeddings are 384-dimensional** (from `all-MiniLM-L6-v2` model)
- **Both** sentence-level (`Claim.decontextualised_claim_embedding`) and document-level (`NLPResult.doc_embedding`) embeddings must be present for retrieval
- **Dummy mode:** If model is unavailable, embeddings must be synthetic (random 384-dim vectors) to preserve schema

### Invariant 5: Job Type Propagation
- **`JobType.USER` or `JobType.BACKGROUND`** is set at API/Ingestor and propagated through all streams
- Services route output to corresponding stream (`user:to.be.X` or `background:to.be.X`)
- **No type mutations:** Job type is read-only after creation

---

## Model Versions & Compatibility

### Current Model Lineup
| Component | Model | Version | Source | Format |
|-----------|-------|---------|--------|--------|
| Embedder | `all-MiniLM-L6-v2` | Latest | Hugging Face | Sentence Transformers |
| NER | `flair/ner-english-large` | Latest | Hugging Face | Flair NER |
| Bias | `unitary/toxic-bert` | Latest | Hugging Face | BERT classifier |

### Compatibility Rules
- **Model swaps:** New model must output same schema (embeddings must be 384-dim, NER must output entities with labels, bias must output bias_score + sentiment_score)
- **No breaking changes:** If swapping models, update `NLP_*_MODEL` env var and run end-to-end tests
- **Schema changes:** If new model produces different output shape, update DTO first, then deploy model

---

## Known Inconsistencies & Gaps

**[INFERRED from codebase audit]**

1. **Stream Payloads Not Documented in Code**
   - Message schemas exist as Python classes but not documented inline
   - Recommendation: Add docstrings to each DTO class with stream-name and direction

2. **Entity Field Names May Differ Across Services**
   - NER output uses `type_of_entity`, but serialization/deserialization may have naming inconsistencies
   - Recent fix (commit `8a56069`) addressed this; verify consistency across all consumers

3. **Bias Detection Output Shape** ✓ RECENT FIX
   - NLI label mapping was corrected in retrieval layer (commit `8a56069`)
   - Monitor for regressions

---

## Checklist for Safe Schema Changes

Before modifying any inter-service message:

- [ ] **Identify all consumers:** Which services read this message? (grep for DTO class name)
- [ ] **Identify all producers:** Which services write this message? (grep for `to.be.X` stream)
- [ ] **Test all paths:** Run end-to-end tests with new schema
- [ ] **Update documentation:** Reflect schema changes in this file
- [ ] **Check dummy modes:** Ensure dummy modes still produce valid schema (e.g., random embeddings are still 384-dim)
- [ ] **Update migration scripts:** If DB schema changes, add PostgreSQL migration
- [ ] **Coordinate with team:** Flag breaking changes in PR description

---

## Schema Versioning Strategy

**Current:** No explicit versioning (V1 assumed)  
**Recommendation:** If major schema changes occur, add version prefix to stream names:
- `user:v1:to.be.nlp` (current)
- `user:v2:to.be.nlp` (future, if incompatible change)

This allows gradual migration without disrupting in-flight messages.
