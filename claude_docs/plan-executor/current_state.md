# Plan Executor — Current Project State

**Last Updated:** 2026-03-26T07:01:15Z

---

**🔄 IMPORTANT:** After completing major work, you MUST update this file and signal the orchestrator via `claude_docs/orchestrator/agent_sync_log.md`. See `claude_docs/orchestrator/AGENT_PROTOCOLS.md` for the synchronization protocol all agents follow.

---

## Your Role
You safely execute structured plans from `claude_docs/` with dependency checking, rollback support, and file modification safety.

## Critical Safety Rules

### Pre-Execution Checklist
- [ ] Plan exists in `claude_docs/` with explicit task dependencies
- [ ] All inter-service schemas documented in `claude_docs/orchestrator/interface_registry.md`
- [ ] Dummy modes verified functional before changing NLP components
- [ ] E2E pipeline traceable: API → Scraper → NLP → Retrieval → DB
- [ ] All file modifications non-destructive with rollback plan

### Shared Interface Freeze
These MUST NOT change without coordinating all consumers:
- Redis stream names (`user:to.be.*`, `background:to.be.*`, `failure:to.be.*`)
- Pydantic DTO shapes (`common/models/api/redis_models.py`)
- SQLAlchemy model fields (`common/models/database/db_models.py`)
- NLP component input/output contracts (order: Preprocessor → CentralityScorer → Embedder → EntityRecognizer → BiasDetector → CheckWorthinessFilter)
- Embedding dimensions (must stay 384-dim for all components)

## Service Entry Points (Verify Before Deployment)

| Service | Entry | Status Check |
|---------|-------|--------------|
| API | `microservices/api/app/main.py` | Listens on port 8001 |
| WebScraper | `microservices/web_scraper/main.py` | Reads from `user:to.be.scraped`, `background:to.be.scraped` |
| NLP | `microservices/nlp/main.py` | Reads from `user:to.be.nlp`, `background:to.be.nlp` |
| Retrieval | `microservices/retrieval_layer/main.py` | Reads from `user:to.be.retrieval`, `background:to.be.retrieval` |
| Ingestor | `microservices/ingestor/main.py` | Produces `background:to.be.scraped` |

## Execution Flow

1. **Read plan** from `claude_docs/*/00_*.md` or specified location
2. **Parse dependencies** — tasks listed with explicit `depends_on`
3. **Check rollback plan** — located at `claude_docs/*/04_rollback_plan.md`
4. **Execute tasks** in dependency order
5. **Verify E2E** — trace full pipeline after each major change
6. **Document results** in execution log

## Common Pitfalls to Avoid

⚠️ **Incomplete Schema Sync** — If you change a DTO, update ALL producers AND consumers  
⚠️ **Dummy Mode Regression** — After NLP changes, always test with `DUMMY_NLP_MODE=True`  
⚠️ **Silent Failures** — Check failure streams (`failure:to.be.*`) after execution  
⚠️ **Embedding Dimension Creep** — Preserve 384-dim for all embeddings (Embedder, sentence, document)

## Reference Documents

- **Plan Templates:** Look for `00_audit.md`, `01_dependency_graph.md`, `02_risk_assessment.md`, `03_execution_plan.md`, `04_rollback_plan.md`
- **Architecture:** `claude_docs/orchestrator/project_state.md`
- **All Schemas:** `claude_docs/orchestrator/interface_registry.md`
- **Remediation Items:** `claude_docs/orchestrator/remediation_plan.md`

## Rollback Safety

Always save:
- Original file contents (git diff for verification)
- Rollback commands in plan's `04_rollback_plan.md`
- Test results before/after for regression detection

---

**Key Principle:** A safe, slow execution is better than a fast failure. Always verify dependencies and trace E2E after each task.
