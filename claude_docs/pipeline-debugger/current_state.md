# Pipeline Debugger — Current Project State

**Last Updated:** 2026-03-26T07:01:15Z

---

**🔄 IMPORTANT:** After completing major work, you MUST update this file and signal the orchestrator via `claude_docs/orchestrator/agent_sync_log.md`. See `claude_docs/orchestrator/AGENT_PROTOCOLS.md` for the synchronization protocol all agents follow.

---

## Your Role
You stress-test the full end-to-end pipeline with diverse articles from multiple news sources, detect regressions, and generate comprehensive debug reports.

## Pipeline Architecture (Verify Current)

```
User/Background Job Submission
    ↓
API Service (port 8001)
    ↓ (API_OUTPUT_STREAM = user:to.be.scraped)
WebScraper (Playwright)
    ↓ (WEB_SCRAPER_USER_OUTPUT_STREAM = user:to.be.nlp)
NLP Service (6-stage pipeline)
    ├─ Preprocessor
    ├─ CentralityScorer
    ├─ Embedder (384-dim vectors via all-MiniLM-L6-v2)
    ├─ EntityRecognizer (flair/ner-english-large)
    ├─ BiasDetector (unitary/toxic-bert)
    └─ CheckWorthinessFilter
    ↓ (NLP_USER_OUTPUT_STREAM = user:to.be.retrieval)
Retrieval Layer
    ↓
PostgreSQL + pgvector (semantic search)
    ↓
Results stored in Redis hash store (retrieval:hash.store)
```

## Test Scenarios (Run Regularly)

### 1. E2E Happy Path
- Submit article via API
- Verify progression through all streams
- Confirm final result in hash store
- Check claims, entities, bias profile all present

### 2. Dummy Modes
- `DUMMY_NLP_MODE=True` — NLP should return synthetic results
- `RETRIEVAL_DUMMY_NLP_MODE=True` — Bypass NLP processing
- `RETRIEVAL_DUMMY_SEED_MODE=True` — Use hardcoded seed data
- All dummy modes must produce valid output shapes

### 3. Priority Handling
- Submit 10 user jobs
- Submit 10 background jobs
- Verify user jobs process first (EXPONENTIAL priority weighting)
- Monitor Redis streams for blocking behavior

### 4. Error Recovery
- Inject malformed message into `user:to.be.scraped`
- Verify error message appears in `failure:to.be.scraped`
- Manually replay from failure stream
- Confirm recovery works

### 5. Embedding Consistency
- Verify all embeddings are 384-dimensional
- Check sentence-level embeddings present in claims
- Check document-level embeddings in NLPResult
- Verify pgvector queries work with embeddings

## Critical Observations to Report

🔴 **BLOCKER:**
- E2E pipeline broken (article stuck in any stream)
- Dummy modes non-functional
- Embeddings not 384-dim
- Failure streams not working

🟡 **REGRESSION:**
- Performance degradation (jobs taking 2x longer)
- NLP component output shape changed
- Claims/entities missing or malformed
- Bias profile empty or invalid

🟢 **WORKING:**
- All stages complete successfully
- Dummy modes produce valid output
- Error recovery works
- Priority handling correct

## Reference Documents

- **Current Schema Contracts:** `claude_docs/orchestrator/interface_registry.md`
- **Architecture Snapshot:** `claude_docs/orchestrator/project_state.md`
- **NLP Pipeline Details:** `.claude/agent-memory/sentinel-orchestrator/nlp_pipeline.md`
- **Known Issues:** `claude_docs/orchestrator/drift_report.md`

## Configuration for Testing

**Key Environment Variables:**
- `COMPOSE_PROFILES=api,scraper,nlp,retrieval` — Start all services
- `USE_GPU=false` — Test on CPU first
- `DUMMY_NLP_MODE=False` — Test real models
- `WEB_SCRAPER_MAX_WORKERS=1` — For deterministic testing
- `NLP_MAX_WORKERS=1` — For deterministic testing

## Debug Output Format

Always include:
- ✓ Date/time of test run (ISO 8601)
- ✓ Which scenarios passed/failed
- ✓ Timeline: job submission → each stream → result
- ✓ Error logs from failure streams
- ✓ Performance metrics (latency per stage)
- ✓ Recommendations for remediation

---

**Trigger:** After major NLP refactoring, significant configuration changes, or when suspected regressions reported.
