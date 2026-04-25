---
## [2026-04-13 00:00] Fix JSON Serialization of Nested Dataclasses in service_template.py

**Date**: April 13, 2026 at 12:00 AM UTC
**Agent**: `claude-inline`
**Branch**: `newretrieval-fixes`
**Triggered By**: Fix "Object of type Entity is not JSON serializable" error when NLP service publishes processed messages to Redis.

### Summary
Changed all three `model_dump()` calls in `service_template.py` to `model_dump(mode='json')` (at lines 100, 154, and 183). This ensures that `MessagePayload` Pydantic models containing nested Python `@dataclass` fields (`List[Claim]`, `List[Entity]`, `Optional[BiasProfile]`) are fully recursively converted to JSON-serializable dicts before being passed to `json.dumps()` for Redis publishing.

### Files Changed
| File Path | Change Type | Description |
|-----------|-------------|-------------|
| `common/service/service_template.py` | Modified | Changed `model_dump()` to `model_dump(mode='json')` at lines 100, 154, and 183 |

### Details
- **Root cause**: Pydantic v2's `model_dump()` (without `mode='json'`) returns raw Python dataclass instances for fields typed as `@dataclass`. `json.dumps()` cannot serialize these, raising `TypeError: Object of type Entity is not JSON serializable`.
- **Fix**: `model_dump(mode='json')` instructs Pydantic v2 to recursively convert all nested dataclass instances to JSON-serializable dicts, matching the serialization behavior required for Redis stream publishing.
- **Affected message fields**: `List[Claim]`, `List[Entity]`, and `Optional[BiasProfile]` inside `MessagePayload`.
- All three call sites in the template are affected: the main processing path and any failure/retry routing paths.

### Pipeline Impact
Affects the NLP service publish step — the boundary between NLP processing and the `user:to.be.retrieval` Redis stream. Without this fix, every NLP-processed message fails to publish, blocking the retrieval stage entirely. Fix restores E2E pipeline flow from NLP → retrieval.

---
