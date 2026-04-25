# Decontextualizer Debug Logging Guide

**Added:** 2026-03-26T07:15:12Z  
**Purpose:** Track decontextualizer behavior to diagnose why ambiguous references remain in output

## Changes Made

Debug logging added to `microservices/nlp/components/decontext.py` to provide visibility into each pipeline phase:

### Phase 2: Unit Extraction
```
Decontextualizer [Phase 2] Sentence: "On Friday, he said..." | Extracted 3 units: ['he', 'Friday', 'said']
```
Shows which ambiguous units spaCy identified in each sentence.

### Phase 5: Q-A Confidence Filtering  
```
Decontextualizer [Phase 6] Sentence 1 unit 2: Q: What does he refer to?... | Score 0.28 < threshold 0.35 → FILTERED
Decontextualizer [Phase 6] Sentence 1: 2 Q-A pairs passed threshold, 1 filtered
```
Reveals which Q-A pairs failed the confidence threshold and why. Low scores here mean:
- BM25 didn't find good evidence, OR
- QA model couldn't answer confidently in the evidence context

### Phase 5.5: BM25 Evidence Retrieval
```
Decontextualizer [BM25] Query: What does he refer to?... | Top scores: [2.1, 1.8, 0.9] | Evidence len: 245
```
Shows BM25 retrieval quality. **Low top scores** (< 1.0) indicate:
- The article doesn't explicitly contain context for this reference
- BM25 couldn't find relevant evidence sentences
- Q-A will likely fail on weak evidence

### Phase 10: Rewrite Rejection Summary
```
Decontextualizer [Phase 10] Sentence 0: Rewrite REJECTED (too_long) | Original: "he said..." | Rewritten: "The president said..." | Len: 45 vs max 36
Decontextualizer [Phase 10 Summary]: Accepted=3, Rejected (empty=0, unchanged=1, has_?=0, too_long=2)
```

Shows why rewrites were rejected:
- **empty** — model produced no output
- **unchanged** — rewritten text matches original (no improvement)
- **has_?** — rewritten text contains "?", indicating incomplete generation
- **too_long** — rewritten text exceeds 4x original length (DECONTEXT_REWRITE_RATIO=4)

## How to Use

### 1. Enable Debug Logging
Set logging level to DEBUG in your NLP service:

```bash
export LOG_LEVEL=DEBUG
python -m microservices.nlp.main
```

Or modify `microservices/nlp/config.py` to set logging level:
```python
logging.basicConfig(level=logging.DEBUG)
```

### 2. Run a Pipeline Test
Submit an article with ambiguous references and capture logs:
```bash
# From API
curl -X POST http://localhost:8001/api/v1/jobs \
  -H "Content-Type: application/json" \
  -d '{"url": "https://...", "enable_decontextualization": true}'

# Watch NLP service logs for decontextualizer output
```

### 3. Interpret the Logs

**If you see many Phase 2 extractions but few Phase 6 acceptances:**
- Problem: Units extracted but Q-A confidence too low
- Action: Try lowering QA_SCORE_THRESHOLD from 0.35 to 0.25

**If you see low BM25 scores (< 1.5):**
- Problem: Evidence not found in article
- Action: Article may lack context; increase top_k in BM25_TOP_K or improve retrieval

**If you see many "too_long" rejections:**
- Problem: Rewritten text exceeds 4x original length
- Action: Lower DECONTEXT_REWRITE_RATIO from 4.0 to 3.0 or 2.5

**If you see many "unchanged" rejections:**
- Problem: Rewriter can't improve the sentence
- Action: May indicate weak Q-A evidence or model limitation

## Configuration Tuning

Based on debug logs, adjust these in `microservices/nlp/config.py`:

```python
# If too few Q-A pairs pass threshold
QA_SCORE_THRESHOLD = 0.25  # down from 0.35

# If evidence retrieval is weak
BM25_TOP_K = 5  # up from 3

# If rewrites too often too long
DECONTEXT_REWRITE_RATIO = 3.0  # down from 4.0

# If too few units extracted
DECONTEXT_MAX_UNITS = 12  # up from 6

# Batch sizes (increase if GPU memory available, decrease if OOM)
DECONTEXT_QG_BATCH_SIZE = 32  # up from 16 (requires more VRAM)
DECONTEXT_QA_BATCH_SIZE = 32
DECONTEXT_GEN_BATCH_SIZE = 32
```

## Example Debug Output

```
[2026-03-26 10:30:45] INFO  Decontextualizer: Phase 1 — spaCy batch parse (7 sentences)...
[2026-03-26 10:30:46] DEBUG Decontextualizer [Phase 2] Sentence: "On Friday, he said the US war..." | Extracted 4 units: ['he', 'Friday', 'US', 'war']
[2026-03-26 10:30:46] DEBUG Decontextualizer [Phase 2] Sentence: "Iran replied that..." | Extracted 2 units: ['Iran', 'replied']
[2026-03-26 10:30:48] INFO  Decontextualizer: Phase 3 done (2.3s)
[2026-03-26 10:30:52] DEBUG Decontextualizer [BM25] Query: What does he refer to?... | Top scores: [0.9, 0.4, 0.2] | Evidence len: 180
[2026-03-26 10:30:52] DEBUG Decontextualizer [Phase 6] Sentence 0 unit 0: Q: What does he... | Score 0.28 < threshold 0.35 → FILTERED
[2026-03-26 10:30:52] DEBUG Decontextualizer [Phase 6] Sentence 0: 1 Q-A pairs passed threshold, 3 filtered
[2026-03-26 10:30:58] INFO  Decontextualizer: Phase 9 done (6.1s)
[2026-03-26 10:30:58] DEBUG Decontextualizer [Phase 10] Sentence 0: Rewrite REJECTED (too_long) | Original: "On Friday, he said..." | Rewritten: "On Friday, President Donald Trump said..." | Len: 58 vs max 44
[2026-03-26 10:30:58] DEBUG Decontextualizer [Phase 10] Sentence 1: Rewrite ACCEPTED | Original: "Iran replied..." → Rewritten: "Iran replied that it would target..."
[2026-03-26 10:30:58] INFO  Decontextualizer [Phase 10 Summary]: Accepted=1, Rejected (empty=0, unchanged=0, has_?=0, too_long=3)
```

In this example:
- 7 sentences, 14 ambiguous units extracted
- Only 4 Q-A pairs passed confidence threshold (10 filtered due to low BM25 evidence)
- Only 1 rewrite accepted (3 rejected as too long)
- **Conclusion:** Increase BM25_TOP_K and lower QA_SCORE_THRESHOLD to improve coverage

## Memory & Context

This guide is saved for future reference. Future debugging sessions should:
1. Enable DEBUG logging
2. Run test articles
3. Reference Phase 2, Phase 6, BM25, and Phase 10 logs to diagnose
4. Adjust config parameters based on patterns observed
5. Re-run test to verify improvements

---

**Related:** `claude_docs/orchestrator/drift_report.md` contains broader decontextualizer findings.

