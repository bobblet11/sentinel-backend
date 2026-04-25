# Sentinel Backend — Current Project State

**Last Updated:** 2026-04-02T00:00:00Z  
**Git HEAD:** `ccb83fa` (newretrieval-fixes) — verified end to end

## Architecture Overview

Sentinel Backend is a **microservices-based fact-checking pipeline** with asynchronous inter-service communication via Redis Streams and PostgreSQL semantic search.

```
┌──────────────────────────────────────────────────────────────────────┐
│                        SENTINEL PIPELINE FLOW                        │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  Client POST /api/v1/jobs  ──→  API Service (port 8001)             │
│                                  (REST endpoint)                    │
│                                        │                            │
│  RSS Ingestor (background jobs) ──→  ┌─┴─────────────────┐          │
│  (background priority lane)           ↓ WebScraper       │          │
│                                  (Playwright)           │          │
│                                        │                │          │
│                                   (user:to.be.nlp)  (bg stream)    │
│                                        │                │          │
│                                        ↓                ↓          │
│                                   ┌─────────────────────┐          │
│                                   │   NLP Pipeline      │          │
│                                   │ (6-stage pipeline)  │          │
│                                   └─────────────────────┘          │
│                                        │                           │
│                                  (user:to.be.retrieval)            │
│                                        │                           │
│                                        ↓                           │
│                                ┌───────────────────┐               │
│                                │ Retrieval Layer   │               │
│                                │ (Semantic Search) │               │
│                                └───────────────────┘               │
│                                        │                           │
│                          Client GET /api/v1/jobs/{uuid}/result     │
│                                        │                           │
└────────────────────────────────────────┴───────────────────────────┘
```

## Microservices Inventory

| Service | Port | Entry Point | Input Streams | Output Streams | Status |
|---------|------|-------------|---------------|----------------|--------|
| **API** | 8001 | `microservices/api/app/main.py` | REST endpoint | `user:to.be.scraped` | ✓ Active |
| **Ingestor** | — | `microservices/ingestor/main.py` | RSS feeds (external) | `background:to.be.scraped` | ✓ Active (one-shot runner) |
| **Web Scraper** | — | `microservices/web_scraper/main.py` | `user:to.be.scraped`, `background:to.be.scraped` | `user:to.be.nlp`, `background:to.be.nlp`, `failure:to.be.scraped` | ✓ Active |
| **NLP** | — | `microservices/nlp/main.py` | `user:to.be.nlp`, `background:to.be.nlp` | `user:to.be.retrieval`, `background:to.be.retrieval`, `failure:to.be.nlp` | ✓ Active |
| **Retrieval** | — | `microservices/retrieval_layer/main.py` | `user:to.be.retrieval`, `background:to.be.retrieval` | `failure:to.be.retrieval` | ✓ Active |

## Redis Streams Architecture

### Namespaces
- **`user:*`** — High-priority streams for user-submitted jobs
- **`background:*`** — Low-priority streams for ingestor/background jobs
- **`failure:*`** — Failure queues for manual intervention and replay

### Stream Names & Payloads

| Stream Name | Direction | Message Type | Consumer | Producer |
|-------------|-----------|--------------|----------|----------|
| `user:to.be.scraped` | → | Article metadata | WebScraper | API Service |
| `background:to.be.scraped` | → | Article metadata | WebScraper | Ingestor |
| `user:to.be.nlp` | → | ScrapedArticle | NLP Service | WebScraper |
| `background:to.be.nlp` | → | ScrapedArticle | NLP Service | WebScraper |
| `user:to.be.retrieval` | → | NLPResult (with embeddings) | Retrieval | NLP Service |
| `background:to.be.retrieval` | → | NLPResult (with embeddings) | Retrieval | NLP Service |
| `failure:to.be.scraped` | → | Article (failed) | Manual | WebScraper |
| `failure:to.be.nlp` | → | ScrapedArticle (failed) | Manual | NLP Service |
| `failure:to.be.retrieval` | → | NLPResult (failed) | Manual | Retrieval |

### Priority Handling
- Services use **`BlockPrioritisationLevel`** enum (EXPONENTIAL, LINEAR) via `prioritised_consumer_combiner.py`
- **EXPONENTIAL** (default): User jobs weighted ~4x higher than background jobs
- **LINEAR**: User jobs weighted 2x higher
- Implementation: Redis blocking read with calculated block times

## NLP Pipeline Components

**Order:** Preprocessor → CentralityScorer → Embedder → EntityRecognizer → BiasDetector → CheckWorthinessFilter

| Component | Type | Input | Output | Model | Dummy Mode | Batch Size |
|-----------|------|-------|--------|-------|------------|------------|
| **Preprocessor** | SentenceProcessor | Article text | Cleaned sentences | spaCy | ✓ Simple split | N/A |
| **CentralityScorer** | SentenceProcessor | Sentences | Scored sentences | TextRank-like | ✓ Synthetic scores | 16 |
| **Embedder** | SentenceProcessor | Sentences | Embeddings (384-dim) | `all-MiniLM-L6-v2` | ✓ Random vectors | 32 |
| **EntityRecognizer** | ArticleProcessor | Article + sentences | Named entities | `flair/ner-english-large` | ✓ Empty list | 16 |
| **BiasDetector** | ArticleProcessor | Article + sentences | Bias profile | `unitary/toxic-bert` | ✓ Neutral profile | N/A |
| **CheckWorthinessFilter** | SentenceProcessor | Scored sentences | Filtered claims | Rule-based | ✓ No filtering | 32 |

**Output DTO:** `NLPResult` — contains `claims_in_article`, `entities_in_article`, `bias_profile`, `doc_embedding`

## Database Schema

### PostgreSQL Tables
- **`articles`** — Article metadata, content, summary, vectors
- **`jobs`** — Job records (user/background), status, timing
- **`results`** — NLP results, claims, entities, bias profiles
- pgvector extension for semantic search

### Redis Storage
- **Hash Store** (namespace: `retrieval:hash.store`) — Job ID → NLPResult mapping
- **Duplicate Filter** (namespace: TBD) — Tracks seen article URLs to prevent reprocessing
- **Consumer Groups** — Per-service consumer group state

## Configuration & Environment

**Key Environment Variables:**
```
# Infrastructure
REDIS_HOST=redis
POSTGRES_HOST=postgres
POSTGRES_DB=sentinel_db

# Service Control
COMPOSE_PROFILES=api,ingestor,scraper,nlp,retrieval  # Which services to start
USE_GPU=false                                         # GPU acceleration for NLP
DUMMY_NLP_MODE=False                                  # Skip NLP models locally

# NLP Models
NLP_EMBEDDING_MODEL=all-MiniLM-L6-v2
NLP_NER_MODEL=flair/ner-english-large
NLP_BIAS_MODEL=unitary/toxic-bert

# Service Scaling
WEB_SCRAPER_MAX_WORKERS=2
NLP_MAX_WORKERS=2
INGESTOR_MAX_WORKERS=10

# Batch Sizes
WEB_SCRAPER_BATCH_SIZE=10
NLP_BATCH_SIZE=10
RETRIEVAL_BATCH_SIZE=10
```

## Docker Image Hierarchy

```
light_python_3_11       light_python_3_12
      ↓                       ↓
common_layer_3_11      common_layer_3_12
      ↓                       ↓
   ┌──┴──┐              ┌──┴──┐
   ↓     ↓              ↓     ↓
CPU_ML  GPU_ML        CPU_ML GPU_ML
(PyTorch, spaCy, transformers)
```

## Key Conventions & Patterns

### Service Base Class
All services inherit from **`ServiceTemplate`** (`common/service/service_template.py`), which provides:
- Redis stream consumption (prioritized or standard)
- Batch processing with configurable batch size
- Worker pool management
- Signal handling (graceful shutdown)
- Failure stream routing
- Message routing (user vs. background job dispatch)

### Model Lifecycle Management
**`ModelManager`** (`common/model_manager/manager.py`) handles:
- Centralized model loading (lazy on first use)
- CUDA → MPS (Mac) → CPU device fallback
- FP16 optimization on CUDA
- Cache management

### Dummy Modes (for local development)
- **`DUMMY_NLP_MODE`** — Disable NLP model loading, return synthetic results
- **`RETRIEVAL_DUMMY_NLP_MODE`** — Bypass NLP in retrieval for testing
- **`RETRIEVAL_DUMMY_SEED_MODE`** — Use hardcoded seed data
- All dummy modes must remain functional

### Error Handling
- Failed messages → failure streams for manual replay
- Graceful degradation (e.g., neutral bias profile on error)
- Explicit logging at stream boundaries (via `common/io/logging.py`)

## Deployment Commands

```bash
./scripts/deploy.sh [base|nlptest|benchmark-1]  # Build & deploy all services
./scripts/clean.sh [base|nlptest|benchmark-1]   # Stop and remove services
./scripts/clear_data.sh                         # Wipe DB and Redis data
./scripts/format_and_lint.sh                    # Format + lint + type check
```

## Known Issues & In-Flight Changes

**As of 2026-03-26:**
- NLP pipeline is undergoing **major refactoring** (branch: `refactor/nlp`)
  - Integration with centralized **ModelManager**
  - Model performance optimizations (bias detection specifically flagged as slow)
- Retrieval layer recently fixed (NLI label mapping, entity field names, atomic hash writes)
- Logging system tuned to INFO level to reduce noise from external libraries

## Health Check Indicators

### Happy Path Traceable?
✓ YES — Full E2E pipeline (scrape → NLP → retrieval → API) is traceable in code.

### Dummy Modes Functional?
✓ YES — All dummy modes verified as wired up (NLP, Retrieval).

### Stream Contracts Consistent?
✓ MOSTLY — See drift report for minor inconsistencies.

### Component Interfaces Clean?
⚠ IN PROGRESS — NLP refactoring is improving this; monitor for drift.
