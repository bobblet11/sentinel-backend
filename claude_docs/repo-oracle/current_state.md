# Repo Oracle — Current Project State

**Last Updated:** 2026-03-26T07:01:15Z

---

**🔄 IMPORTANT:** After completing major work, you MUST update this file and signal the orchestrator via `claude_docs/orchestrator/agent_sync_log.md`. See `claude_docs/orchestrator/AGENT_PROTOCOLS.md` for the synchronization protocol all agents follow.

---

## Your Role
You are the authoritative source for repository knowledge: Docker configuration, bash scripts, service dependencies, environment variables, microservice architecture, Redis streams, NLP pipelines, deployment workflows, and testing strategies.

## Quick Repository Facts

**Root Directory Structure:**
- `microservices/` — 5 services (api, ingestor, web_scraper, nlp, retrieval_layer)
- `common/` — Shared libraries (models, redis_client, service_template, model_manager, io, env, requests, process, constants)
- `docker/` — Container images (8 Dockerfiles) + docker-compose.yml
- `scripts/` — Deployment & operations (deploy.sh, clean.sh, clear_data.sh, format_and_lint.sh, etc.)
- `configs/` — Environment templates (.env.template, nlptest/, benchmark-1/)
- `tests/` — Sprint-organized tests (tests/sprint0/ through tests/sprint4/, benchmarks/)
- `claude_docs/orchestrator/` — Authoritative architecture documentation

## Microservices Quick Reference

| Service | Port | Language | Entry | Input Streams | Output Streams |
|---------|------|----------|-------|---------------|----------------|
| API | 8001 | Python | `microservices/api/app/main.py` | REST (HTTP) | `user:to.be.scraped` |
| Ingestor | — | Python | `microservices/ingestor/main.py` | RSS feeds (external) | `background:to.be.scraped` |
| WebScraper | — | Python | `microservices/web_scraper/main.py` | `user:to.be.scraped`, `background:to.be.scraped` | `user:to.be.nlp`, `background:to.be.nlp`, `failure:to.be.scraped` |
| NLP | — | Python | `microservices/nlp/main.py` | `user:to.be.nlp`, `background:to.be.nlp` | `user:to.be.retrieval`, `background:to.be.retrieval`, `failure:to.be.nlp` |
| Retrieval | — | Python | `microservices/retrieval_layer/main.py` | `user:to.be.retrieval`, `background:to.be.retrieval` | `failure:to.be.retrieval` (hash store) |

## Docker Image Hierarchy

```
light_python_3_11 / light_python_3_12
  ↓
common_layer_3_11 / common_layer_3_12 (+ pip dependencies)
  ├→ CPU_ML_base (+ PyTorch, spaCy, transformers)
  └→ GPU_ML_base (+ PyTorch GPU CUDA 12.1, same ML libs)
```

## Environment Variables (Key)

### Infrastructure
```
REDIS_HOST=redis
REDIS_PORT=6379
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=sentinel_db
POSTGRES_USER=sentinel
POSTGRES_PASSWORD=sentinelpass
```

### Services & Streams
```
API_SERVICE_PORT=8001
API_OUTPUT_STREAM=user:to.be.scraped

WEB_SCRAPER_INPUT_STREAMS=user:to.be.scraped,background:to.be.scraped
WEB_SCRAPER_USER_OUTPUT_STREAM=user:to.be.nlp
WEB_SCRAPER_BACKGROUND_OUTPUT_STREAM=background:to.be.nlp
WEB_SCRAPER_BATCH_SIZE=10
WEB_SCRAPER_MAX_WORKERS=2

NLP_INPUT_STREAMS=user:to.be.nlp,background:to.be.nlp
NLP_USER_OUTPUT_STREAM=user:to.be.retrieval
NLP_BACKGROUND_OUTPUT_STREAM=background:to.be.retrieval
NLP_EMBEDDING_MODEL=all-MiniLM-L6-v2
NLP_NER_MODEL=flair/ner-english-large
NLP_BIAS_MODEL=unitary/toxic-bert
USE_GPU=false
NLP_BASE=sentinel/python-ml-cpu:3.12

RETRIEVAL_INPUT_STREAMS=user:to.be.retrieval,background:to.be.retrieval
HASH_STORE_NAMESPACE=retrieval:hash.store
```

## Deployment Commands

```bash
./scripts/deploy.sh base                # Deploy with base config
./scripts/deploy.sh nlptest             # Deploy with nlptest config
./scripts/deploy.sh benchmark-1         # Deploy with benchmark config
./scripts/clean.sh base                 # Stop all containers
./scripts/clear_data.sh                 # Wipe all data (DB + Redis)
./scripts/format_and_lint.sh            # Format + lint + type check
```

## Testing Commands

```bash
pytest tests/                           # Run all tests
pytest tests/sprint4/                   # Run sprint 4 tests
pytest tests/benchmarks/                # Run benchmark tests
```

## Redis Streams Namespace

```
user:to.be.scraped                      (HIGH priority)
user:to.be.nlp
user:to.be.retrieval
background:to.be.scraped                (LOW priority)
background:to.be.nlp
background:to.be.retrieval
failure:to.be.scraped                   (Manual replay)
failure:to.be.nlp
failure:to.be.retrieval
```

## NLP Pipeline (6 Stages)

1. **Preprocessor** → Cleans text, splits into sentences
2. **CentralityScorer** → Ranks sentence importance
3. **Embedder** → `all-MiniLM-L6-v2` (384-dim vectors)
4. **EntityRecognizer** → `flair/ner-english-large` (extracts people, places, orgs)
5. **BiasDetector** → `unitary/toxic-bert` (political bias classification)
6. **CheckWorthinessFilter** → Rule-based claim filtering

## Common File Locations

| Purpose | Path |
|---------|------|
| Service base class | `common/service/service_template.py` |
| Model lifecycle mgmt | `common/model_manager/manager.py` |
| API DTOs | `common/models/api/dtos/` |
| Database models | `common/models/database/db_models.py` |
| Redis client | `common/redis_client/` |
| Logging | `common/io/logging.py` |
| Environment config | `configs/.env.template` |
| Docker compose | `docker/compose/docker-compose.yml` |
| API endpoints | `microservices/api/app/api/v1/endpoints/` |
| NLP components | `microservices/nlp/components/` |

## Architecture Sources of Truth

- **Full Architecture:** `claude_docs/orchestrator/project_state.md`
- **All Schemas:** `claude_docs/orchestrator/interface_registry.md`
- **Drift/Issues:** `claude_docs/orchestrator/drift_report.md`
- **Remediation:** `claude_docs/orchestrator/remediation_plan.md`

## Common Questions Answered

**Q: How do services communicate?**  
A: Redis Streams. Producers publish to `user:*` or `background:*` queues; consumers read via consumer groups. See `common/redis_client/` for producer/consumer logic.

**Q: Where are models stored?**  
A: Lazily loaded from Hugging Face during service startup. Managed by `ModelManager` in `common/model_manager/manager.py`. Supports CUDA/MPS/CPU fallback.

**Q: What's the E2E latency?**  
A: Full pipeline (API submission → result) depends on article size and model performance. Bias detection flagged as slow (commit 49cff7d). See pipeline-debugger for performance profiling.

**Q: How do dummy modes work?**  
A: Set `DUMMY_NLP_MODE=True` to skip model loading; components return synthetic results. Enables local dev without GPU. Check each component's dummy mode logic in `microservices/nlp/components/`.

---

**Your Authority:** You are the repository's keeper of operational knowledge. When asked about configuration, deployment, dependencies, or structure, always answer with precision and direct users to relevant files.
