---
## [2026-04-01 12:00] Rename torch_dtype to dtype in BiasDetector pipeline() Calls

**Date**: April 1, 2026 at 12:00 PM UTC
**Agent**: `claude-inline`
**Branch**: `newretrieval-fixes`
**Triggered By**: Silence deprecation warnings from the transformers library in BiasDetector; future-proof against the kwarg being removed in a future transformers release.

### Summary
Both `pipeline()` calls inside `BiasDetector.__init__` were updated to use the current `dtype=` keyword argument in place of the now-deprecated `torch_dtype=` kwarg. The transformers library renamed this parameter in its pipeline() API; the old name currently emits a deprecation warning and will become an error in a future release. No behavioural change.

### Files Changed
| File Path | Change Type | Description |
|-----------|-------------|-------------|
| `microservices/nlp/components/bias.py` | Modified | Replaced `torch_dtype=device_config.dtype` with `dtype=device_config.dtype` on both pipeline() calls: `political_classifier` (line 74) and `sentiment_analyzer` (line 80) |

### Details
- The fix is purely a kwarg rename — no logic, model, device placement, or data-type behaviour changes.
- Both pipelines (`zero-shot-classification` political classifier and `sentiment-analysis` sentiment analyzer) were affected identically.
- This is analogous to the `fix-ner-accelerate-device-conflict` task, which audited `ner.py` for related pipeline() API issues; the memory note from that task flagged `BiasDetector` as a candidate for this audit.
- Dummy mode is unaffected (BiasDetector is skipped in dummy mode).
- No consumers of `BiasDetector` outputs need updating — the `BiasProfile` schema is unchanged.

### Pipeline Impact
NLP — BiasDetector component only. No functional change; deprecation warning silenced. No stream interfaces, Pydantic schemas, or DB models touched. E2E pipeline stability unaffected.

---
