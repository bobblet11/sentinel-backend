# Systems Planner — Current Project State

**Last Updated:** 2026-03-26T07:01:15Z

---

**🔄 IMPORTANT:** After completing major work, you MUST update this file and signal the orchestrator via `claude_docs/orchestrator/agent_sync_log.md`. See `claude_docs/orchestrator/AGENT_PROTOCOLS.md` for the synchronization protocol all agents follow.

---

## Your Role
You audit complex changes before implementation, map dependencies, assess risks, and generate detailed task plans for significant engineering work.

## Current Priority Areas

### 1. NLP Pipeline Refactoring (refactor/nlp branch)
**Status:** In-flight, ~70% complete  
**What:** Centralizing model loading via `ModelManager`  
**Why:** Performance — lazy load, cache, device fallback (CUDA → MPS → CPU)  
**Your focus:** When tasked, verify all 6 NLP components properly migrate to centralized ModelManager; flag any race conditions or incomplete integrations

### 2. Known Dependencies & Blast Radius
- **ServiceTemplate** (`common/service/service_template.py`) — Base class for ALL 5 services. Changes here cascade to: API, WebScraper, NLP, Retrieval, Ingestor
- **Redis Stream Names** — Changes to `user:to.be.*`, `background:to.be.*`, `failure:to.be.*` affect all consumers
- **Pydantic DTOs** (`common/models/api/`) — All producers and consumers must be updated in sync
- **NLP Component Contracts** — All 6 components share input/output shapes; changes require E2E testing

## Critical Interface Boundaries

### Redis Streams (Priority Order)
```
user:to.be.scraped (HIGH)   → user:to.be.nlp → user:to.be.retrieval
background:to.be.scraped    → background:to.be.nlp → background:to.be.retrieval
failure:to.be.*             → Manual replay queue
```

### NLP Pipeline Contract (DO NOT CHANGE ORDER)
1. **Preprocessor** → Sentences
2. **CentralityScorer** → Scored sentences
3. **Embedder** → 384-dim embeddings (CRITICAL: must stay 384)
4. **EntityRecognizer** → Named entities with types
5. **BiasDetector** → BiasProfile (category, score, sentiment)
6. **CheckWorthinessFilter** → Filtered claims

## Planning Checklist

When asked to plan a change, verify:
- ✓ All downstream consumers of modified interfaces
- ✓ Embedding dimensions preserved (384-dim)
- ✓ Dummy modes still functional after changes
- ✓ E2E pipeline remains traceable (API → Scraper → NLP → Retrieval → DB)
- ✓ All failure stream paths still working
- ✓ No circular dependencies introduced

## Reference Documents

- **Architecture:** `claude_docs/orchestrator/project_state.md`
- **All Schemas:** `claude_docs/orchestrator/interface_registry.md`
- **Current Issues:** `claude_docs/orchestrator/drift_report.md`
- **Action Items:** `claude_docs/orchestrator/remediation_plan.md`

## Risk Flags

🚩 **ModelManager Integration** — Incomplete; verify before shipping  
🚩 **Schema Versioning** — No versioning strategy; major changes could break in-flight messages  
🚩 **Failure Stream Replay** — Not thoroughly tested; low confidence in error recovery path

---

**Next Actions:** Check orchestrator/remediation_plan.md for Priority 1-4 items when planning new work.
