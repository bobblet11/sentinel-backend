---
## [2026-04-01 00:02] Fix NER Pipeline ValueError: Remove Redundant `device=` Arg When Using Accelerate

**Date**: April 1, 2026 at 12:02 AM UTC
**Agent**: `claude-inline`
**Branch**: `newretrieval-fixes`
**Triggered By**: Runtime `ValueError` during NLP pipeline test (`run_pipeline_tests.py`) — NER model failed to load because `device=` was passed to `pipeline()` alongside `device_map` managed by accelerate.

### Summary
Removed the `device=device_config.device_id` keyword argument from the `pipeline("ner", ...)` constructor call in `EntityRecognizer.__init__`. The model was already placed on the correct device by accelerate via `device_map={"": device}`, making the additional `device=` argument both redundant and invalid — Hugging Face raises a `ValueError` when both are present.

### Files Changed
| File Path | Change Type | Description |
|-----------|-------------|-------------|
| `microservices/nlp/components/ner.py` | Modified | Removed `device=device_config.device_id` from the `pipeline("ner", ...)` constructor call (line 41 pre-fix). No other changes. |

### Details
- Root cause: `DeviceConfig.device_map` (defined in `microservices/nlp/components/device.py`, lines 65–67) always returns `{"": self.device}`, so accelerate is always engaged regardless of CPU or GPU mode.
- When accelerate owns device placement via `device_map`, passing `device=` to the Hugging Face `pipeline()` triggers: `ValueError: The model has been loaded with accelerate and therefore cannot be moved to a specific device`.
- The fix is a single-argument removal; no logic changes, no interface changes, and no new imports.
- Dummy mode is unaffected — `EntityRecognizer` is not instantiated in dummy mode.
- Related component `BiasDetector` should be audited to confirm it does not have the same pattern (`device=` alongside `device_map` in its pipeline call).

### Pipeline Impact
NLP — `EntityRecognizer` component (Named Entity Recognition stage). The E2E pipeline was broken at the NER stage prior to this fix; the fix restores NER model loading on both CPU and GPU. No Pydantic schema, Redis stream shape, or DB model was changed.

---
