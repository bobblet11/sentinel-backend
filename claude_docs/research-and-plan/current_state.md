# Research & Plan — Current Project State

**Last Updated:** 2026-03-26T07:01:15Z

---

**🔄 IMPORTANT:** After completing major work, you MUST update this file and signal the orchestrator via `claude_docs/orchestrator/agent_sync_log.md`. See `claude_docs/orchestrator/AGENT_PROTOCOLS.md` for the synchronization protocol all agents follow.

---

## Your Role
You research implementation approaches before committing to solutions, especially for NLP pipeline improvements and architectural changes. You evaluate libraries, models, and algorithms before planning.

## Current Active Research Topics

### 1. NLP Pipeline Component Swaps
**Current State:** All 6 components have pluggable model slots  
**Candidates for Research:**
- Embedder: Can we swap `all-MiniLM-L6-v2` (384-dim) for a larger model? (⚠️ Constraint: MUST preserve 384-dim or update all downstream code)
- NER: `flair/ner-english-large` performs well; research cost/benefit of alternatives
- Bias Detector: `unitary/toxic-bert` is slow per commit history; research faster alternatives (must preserve output schema)

**Your Role:** When asked to research, evaluate:
- Model accuracy/performance tradeoffs
- Embedding dimensions (constraint: 384-dim critical)
- Inference latency (bias detection flagged as slow)
- Device requirements (GPU/CPU fallback needed)
- Deployment complexity

### 2. Schema Evolution Strategies
**Problem:** No versioning for breaking schema changes; in-flight messages could be corrupted if schema changes mid-stream

**Research Questions:**
- How to version Redis stream messages without disrupting in-flight jobs?
- What's the pattern: `user:v1:to.be.nlp` vs. header versioning vs. union types?
- Can we achieve backward compatibility with Pydantic?

### 3. Error Recovery Pipeline
**Problem:** Failure stream replay logic not tested; manual recovery procedures undocumented

**Research Scope:**
- Replay semantics: Should failed messages be processed in original order or FIFO?
- Idempotency: Are all pipeline stages idempotent? (e.g., biasing the same article twice)
- Recovery orchestration: Who triggers replay — manual, automatic, time-based?

## Research Quality Checklist

When starting a research project, verify you'll deliver:

✓ **Problem Statement** — What are we solving and why?  
✓ **Solution Space** — 3+ viable approaches with tradeoffs  
✓ **Evaluation Criteria** — How do we measure "better"?  
✓ **Implementation Complexity** — Effort to integrate each option  
✓ **Risk Assessment** — What could break?  
✓ **Recommendation** — Which option to pursue and why  

## Reference Architecture

### NLP Pipeline (Immutable Order)
1. Preprocessor (spaCy-based sentence splitting)
2. CentralityScorer (TextRank-like importance)
3. Embedder (all-MiniLM-L6-v2, 384-dim) ← **Critical: 384-dim preserved**
4. EntityRecognizer (flair/ner-english-large)
5. BiasDetector (unitary/toxic-bert) ← **Flagged: Performance bottleneck**
6. CheckWorthinessFilter (rule-based claim filtering)

### Output DTO Contract
```python
NLPResult:
  - claims_in_article: List[Claim]
  - entities_in_article: List[Entity]
  - bias_profile: BiasProfile
  - doc_embedding: List[float]  # Must be 384-dim
```

## Known Constraints (Do Not Violate)

🔴 **Hard Constraints:**
- Embeddings MUST stay 384-dimensional (all-MiniLM-L6-v2 → any swap → must be 384-dim)
- NLP component order MUST NOT change (Preprocessor → ... → CheckWorthinessFilter)
- Dummy modes MUST remain functional
- E2E pipeline MUST stay traceable

🟡 **Soft Constraints:**
- Prefer models from Hugging Face for consistency
- Keep GPU/CPU fallback support (CUDA → MPS → CPU)
- Maintain <5s total latency for full pipeline (bias detection is slow; optimize if possible)

## Output Format

When delivering research:
1. **Executive Summary** — 1 paragraph, recommendation
2. **Option Analysis** — 3+ options with pros/cons
3. **Implementation Complexity** — Estimated effort per option
4. **Risk Assessment** — What could go wrong
5. **Recommendation** — Which option + why
6. **Next Steps** — Delegate to systems-planner for planning

## Reference Documents

- **NLP Pipeline Details:** `.claude/agent-memory/sentinel-orchestrator/nlp_pipeline.md`
- **Interface Contracts:** `claude_docs/orchestrator/interface_registry.md`
- **Current Issues:** `claude_docs/orchestrator/drift_report.md`
- **Known Remediation:** `claude_docs/orchestrator/remediation_plan.md`

---

**Key Principle:** Thorough research now prevents costly mistakes later. Always document alternatives and evaluate them rigorously before recommending.
