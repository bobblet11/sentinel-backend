# BiasDetector Fix Plan: Bug Fixes + Model Upgrade

**Date:** 2026-04-12
**Author:** research-and-plan agent
**Research:** `/workspaces/sentinel-backend/claude_docs/research-and-plan/bias-detector-model-evaluation-2026-04-12.md`
**Status:** Ready for execution

---

## Overview

Fix 5 bugs making BiasDetector non-operational and upgrade the political bias model from a generic zero-shot NLI model to a purpose-trained political bias classifier.

**Model change:** `typeform/distilbert-base-uncased-mnli` (zero-shot, ~76% acc) --> `premsa/political-bias-prediction-allsides-BERT` (direct 3-class, F1=0.904)

---

## Interface Audit Summary (2026-04-12)

An independent interface audit was run after initial plan creation. Findings:

| Contract | Status | Notes |
|---|---|---|
| `BiasProfile` dataclass fields | ✓ Correct | All 5 fields Optional, types match plan |
| `StreamMessage.create_nlp_result()` / `set_nlp_result()` | ✓ Correct | `if not` guards work safely with Step 1 fix |
| `NLPOptions.enable_bias_detection` | ⚠ Gap found | Retrieval layer crashes when `bias_profile=None` |
| `ClaimExtraction` Stage 7→8 state merge | ✓ Correct | `create_nlp_result()` copy preserves Stage 7 claims |
| `DeviceConfig.device_id` / `.dtype` attributes | ✓ Correct | Attributes exist with correct types |
| `premsa/...` model output format (`top_k=None`) | ⚠ Unverified | Must verify `id2label` mapping before implementing Step 3 |
| DB persistence (`SentimentAnalysis` table) | ✓ Correct | Fields extracted individually, not stored as object |
| API response DTOs (`jobs.py._build_bias_analysis`) | ✓ Correct | Handles `None` gracefully |
| Retrieval layer (`retrieval_service.py:134`) | **❌ CRITICAL GAP** | `bias_profile.bias_category` crashes if `bias_profile is None` |
| `MessagePayload` Pydantic + `asdict()` | ✓ Correct | Standard dataclass serialisation |

**Two gaps added as Step 1.5 and a pre-check on Step 3:**
- **Step 1.5 (new):** Guard `retrieval_service.py:134` against `None` bias_profile — this crashes in production if bias detection is disabled or fails
- **Step 3 pre-check (new):** Verify `premsa/political-bias-prediction-allsides-BERT` `id2label` mapping before changing `_POLITICAL_LABEL_MAP`

---

## Execution Order

Changes are ordered to minimize risk. Each step leaves the codebase in a working state.

### Step 1: Fix Bug 1 -- NameError in exception handler
**File:** `microservices/nlp/components/bias.py`
**Priority:** CRITICAL -- this causes a secondary exception that swallows the real error

**Current code (lines 131-154):**
```python
analysis_text = text[:BIAS_MAX_CHARS]

# -- Political Bias --
try:
    bias_out = self.political_classifier(...)
    ...
    scores: Dict[str, float] = {...}
    political_bias = ...
except Exception as e:
    logger.error(...)
    result.bias_profile = self._neutral_profile()  # NameError: `result` undefined
    return
```

**Fix:** Create `result` before the try block. Move `result = message.create_nlp_result()` from line 177 up to before line 134. In the except block, after setting neutral profile, call `message.set_nlp_result(result)` before returning.

**Changed code:**
```python
analysis_text = text[:BIAS_MAX_CHARS]
result = message.create_nlp_result()

# -- Political Bias --
try:
    bias_out = self.political_classifier(...)
    ...
    scores: Dict[str, float] = {...}
    political_bias = ...
except Exception as e:
    logger.error(f"BiasDetector: Political bias classification failed: {e}")
    result.bias_profile = self._neutral_profile()
    message.set_nlp_result(result)
    return
```

Then at line 177, change `result = message.create_nlp_result()` to just use the existing `result` variable (remove the re-creation).

**Verification:** The except handler now uses a valid `result` object and persists it. Graceful degradation works as documented.

---

### Step 1.5 (NEW): Guard retrieval layer against None bias_profile
**File:** `microservices/retrieval_layer/services/retrieval_service.py`
**Priority:** CRITICAL -- crashes with `AttributeError` if bias_profile is None (e.g., when `enable_bias_detection=False` after Step 2's lazy-init, or on any bias stage failure)

**Current code (line 131-134):**
```python
bias_profile = message.bias_profile
article_dto = CreateOrModifyArticle(...)
sentiment_dto = CreateOrModifySentiment(
    bias_profile.bias_category,        # ← AttributeError if None
    bias_profile.bias_score,
    bias_profile.bias_analysis_confidence,
    bias_profile.sentiment_category,
    bias_profile.sentiment_analysis_confidence
)
```

**Fix:**
```python
bias_profile = message.bias_profile
if bias_profile is None:
    from common.models.api.redis_models import BiasProfile
    bias_profile = BiasProfile(
        bias_category="Center",
        bias_score=0.0,
        bias_analysis_confidence=0.0,
        sentiment_category="Neutral",
        sentiment_analysis_confidence=0.0,
    )
sentiment_dto = CreateOrModifySentiment(
    bias_profile.bias_category,
    bias_profile.bias_score,
    bias_profile.bias_analysis_confidence,
    bias_profile.sentiment_category,
    bias_profile.sentiment_analysis_confidence
)
```

**Verification:** Retrieval service processes articles without a bias_profile (dummy mode, disabled bias, or bias stage failure) without crashing.

---

### Step 2: Fix Bug 5 -- Unconditional model loading
**File:** `microservices/nlp/components/claimextract.py`
**Priority:** HIGH -- wastes ~760MB memory when bias detection is disabled

**Current code (line 86):**
```python
self.bias_detector = BiasDetector(device_config=device_config, model_manager=model_manager)
```

**Fix:** Store constructor args and lazily initialize BiasDetector at stage 8.

**Changed code in `__init__`:**
```python
# Store for lazy initialization of BiasDetector (Stage 8)
self._bias_device_config = device_config
self._bias_model_manager = model_manager
self._bias_detector = None
```

**Changed code in `run()` at Stage 8 (around line 280):**
```python
if options.enable_bias_detection:
    if self._bias_detector is None:
        self._bias_detector = BiasDetector(
            device_config=self._bias_device_config,
            model_manager=self._bias_model_manager,
        )
    t = time.time()
    try:
        message.add_timestamp(JobStage.BIAS_ANAL_IN)
        self._bias_detector.run(article, message, options)
        ...
```

Remove line 86 (`self.bias_detector = BiasDetector(...)`) and replace `self.bias_detector` references with `self._bias_detector`.

**Note:** The first article with bias enabled will pay the BiasDetector construction cost. This is fine because the heavy part (model loading) is handled by ModelManager during `load_all()` -- BiasDetector's `__init__` just retrieves already-loaded models from the manager.

**Verification:** When `enable_bias_detection=False`, no BiasDetector is created and no bias models are retrieved from ModelManager.

---

### Step 3: Upgrade political bias model
**Pre-implementation check (REQUIRED before writing code):**
Verify the `id2label` mapping of `premsa/political-bias-prediction-allsides-BERT` matches the plan's assumption:
```bash
python -c "
from transformers import AutoConfig
cfg = AutoConfig.from_pretrained('premsa/political-bias-prediction-allsides-BERT')
print(cfg.id2label)
"
```
Expected: `{0: 'Left', 1: 'Center', 2: 'Right'}` (or equivalent LABEL_0/LABEL_1/LABEL_2 mapping).
If the mapping differs, update `_POLITICAL_LABEL_MAP` in `bias.py` to match actual labels before continuing.


**Files:** `microservices/nlp/config.py`, `common/model_manager/manager.py`, `microservices/nlp/components/bias.py`

#### 3a. Update config constant
**File:** `microservices/nlp/config.py` line 27

**Change:**
```python
# Before
BIAS_POLITICAL_MODEL = "typeform/distilbert-base-uncased-mnli"

# After
BIAS_POLITICAL_MODEL = "premsa/political-bias-prediction-allsides-BERT"
```

#### 3b. Update ModelManager registration
**File:** `common/model_manager/manager.py` lines 70-82

**Change the BIAS_POLITICAL ModelEntry:**
```python
ModelEntry(
    key="BIAS_POLITICAL",
    model_name=os.environ.get(
        "NLP_BIAS_MODEL",
        "premsa/political-bias-prediction-allsides-BERT",
    ),
    task_type="text_classification",  # was "zero_shot_classification"
    owner_component="BiasDetector",
    loader="transformers_pipeline",
    device_policy=DevicePolicy.PREFER_GPU,
    required=False,
    estimated_memory_mb=440,  # was 260 (BERT-base is larger than DistilBERT)
    loader_kwargs={"top_k": None},  # return all class scores
),
```

#### 3c. Update `_resolve_hf_task` method
**File:** `common/model_manager/manager.py` lines 406-421

The current special case at line 408 checks `entry.key in ("BIAS", "BIAS_POLITICAL")` and looks for "mnli" in the model name. Since we're switching away from MNLI, this special case must be updated.

**Change:**
```python
def _resolve_hf_task(self, entry: ModelEntry) -> str:
    """Map a ModelEntry's task_type to the HuggingFace pipeline task string."""
    _TASK_MAP = {
        "zero_shot_classification": "zero-shot-classification",
        "token_classification": "token-classification",
        "text_classification": "text-classification",
        "sentiment_analysis": "sentiment-analysis",
    }
    return _TASK_MAP.get(entry.task_type, entry.task_type)
```

Remove the entire `if entry.key in ("BIAS", "BIAS_POLITICAL")` special case block. The `_TASK_MAP` handles the mapping cleanly via `task_type`.

#### 3d. Update BiasDetector to use direct classification
**File:** `microservices/nlp/components/bias.py`

**Major changes to the class:**

1. Remove `POLITICAL_LABELS` class constant (no longer needed for zero-shot)
2. Update `_LABEL_MAP` to map model output label IDs:
```python
# premsa/political-bias-prediction-allsides-BERT outputs:
#   LABEL_0 = Left, LABEL_1 = Center, LABEL_2 = Right
_POLITICAL_LABEL_MAP = {
    "LABEL_0": "Left",
    "LABEL_1": "Center",
    "LABEL_2": "Right",
}
```

3. Update the political bias section of `run()`:
```python
# -- Political Bias (direct classification) --
try:
    bias_out = self.political_classifier(
        analysis_text,
        truncation=True,
        max_length=512,
    )
    # bias_out is a list of dicts: [{"label": "LABEL_0", "score": 0.8}, ...]
    # Sort by score descending
    bias_out_sorted = sorted(bias_out, key=lambda x: x["score"], reverse=True)
    raw_label = bias_out_sorted[0]["label"]
    confidence = float(bias_out_sorted[0]["score"])

    scores: Dict[str, float] = {
        self._POLITICAL_LABEL_MAP.get(item["label"], "Center"): float(item["score"])
        for item in bias_out_sorted
    }
    political_bias = self._POLITICAL_LABEL_MAP.get(raw_label, "Center")

except Exception as e:
    logger.error(f"BiasDetector: Political bias classification failed: {e}")
    result.bias_profile = self._neutral_profile()
    message.set_nlp_result(result)
    return
```

4. Update fallback `__init__` path (when no ModelManager) to use `text-classification` pipeline:
```python
self.political_classifier = pipeline(
    "text-classification",
    model=BIAS_POLITICAL_MODEL,
    device=device_config.device_id,
    dtype=device_config.dtype,
    top_k=None,  # return all class scores
)
```

5. Update docstring to reflect the new model and approach.

**Verification:** The output still produces a `BiasProfile` with `bias_category` in `{"Left", "Center", "Right"}` -- no downstream schema changes needed.

---

### Step 4: Fix Bug 2 -- Wrong model key in test
**File:** `microservices/nlp/tests/debug_articles/test_components.py` line 150

**Change:**
```python
# Before
COMPONENT_MODEL_KEYS = {
    ...
    "bias": ["SPACY_SENT", "EMBEDDING", "BIAS"],
    ...
    "all": ["SPACY_SENT", "EMBEDDING", "NER", "BIAS", "CHECKWORTHY"],
}

# After
COMPONENT_MODEL_KEYS = {
    ...
    "bias": ["SPACY_SENT", "EMBEDDING", "BIAS_POLITICAL", "BIAS_SENTIMENT"],
    ...
    "all": ["SPACY_SENT", "EMBEDDING", "NER", "BIAS_POLITICAL", "BIAS_SENTIMENT", "CHECKWORTHY"],
}
```

Also update `test_components.py` line 74 to match the new default model:
```python
# Before
os.environ["NLP_BIAS_MODEL"] = "typeform/distilbert-base-uncased-mnli"

# After
os.environ["NLP_BIAS_MODEL"] = "premsa/political-bias-prediction-allsides-BERT"
```

---

### Step 5: Fix Bug 3 -- Test harness interface mismatch
**File:** `microservices/nlp/tests/debug_articles/test_components.py`

**Problem 1:** `BiasDetector()` called with no args at line 311, but requires `device_config`.
**Problem 2:** `component.run(article, result, options)` passes `NLPResult`, but BiasDetector expects `StreamMessage`.

**Fix:** Refactor `run_component()` to handle component-specific constructor args and call signatures.

**Changed imports (add):**
```python
from common.models.api.redis_models import (
    Article, NLPOptions, NLPResult, SentenceScore,
    StreamMessage, Message, MessageHeader, MessagePayload,
)
from microservices.nlp.config import DEVICE_CONFIG, model_manager
```

**Add a helper to create a test StreamMessage:**
```python
def _make_test_stream_message(article: Article) -> StreamMessage:
    """Create a minimal StreamMessage for testing components that require it."""
    import uuid
    header = MessageHeader(
        uid=str(uuid.uuid4()),
        type="user",
        status="processing",
        created_at="2026-01-01T00:00:00Z",
    )
    payload = MessagePayload(
        article_url=article.link,
        parsed_text=article.text,
        title=article.title,
        summary=article.summary,
        news_outlet=article.source,
    )
    message = Message(header=header, payload=payload, stage_timestamps=[])
    return StreamMessage(stream="test", redis_id="0-0", priority=1, data=message)
```

**Refactor `run_component()`:**
```python
def run_component(
    name: str,
    article: Article,
    result: NLPResult,
    options: NLPOptions,
    sentences: list,
):
    """Instantiate and run a single component. Returns (elapsed, sentences)."""
    cls = COMPONENT_CLASSES[name]
    ctype = COMPONENT_TYPES[name]

    # Components that need constructor args
    if name == "bias":
        component = cls(device_config=DEVICE_CONFIG, model_manager=model_manager)
    elif name == "ner":
        component = cls(device_config=DEVICE_CONFIG, model_manager=model_manager)
    elif name == "embedder":
        component = cls(device_config=DEVICE_CONFIG, model_manager=model_manager)
    elif name == "checkworthy":
        component = cls(device_config=DEVICE_CONFIG)
    else:
        component = cls()

    t0 = time.monotonic()

    # ArticleProcessor takes StreamMessage, not NLPResult
    if ctype == "ArticleProcessor":
        message = _make_test_stream_message(article)
        # Pre-populate message with current pipeline state
        msg_result = message.create_nlp_result()
        msg_result.claims_in_article = result.claims_in_article
        msg_result.entities_in_article = result.entities_in_article
        msg_result.bias_profile = result.bias_profile
        message.set_nlp_result(msg_result)

        component.run(article, message, options)

        # Copy results back to the local NLPResult
        updated = message.create_nlp_result()
        result.bias_profile = updated.bias_profile
        result.entities_in_article = updated.entities_in_article
    elif ctype == "SentenceGenerator":
        # Preprocessor also takes StreamMessage
        message = _make_test_stream_message(article)
        sentences = component.run(article, message, options)
    elif ctype == "SentenceProcessor":
        message = _make_test_stream_message(article)
        sentences = component.run(article, message, options, sentences)
    elif ctype == "SentenceConsumer":
        message = _make_test_stream_message(article)
        component.run(article, message, options, sentences)
        updated = message.create_nlp_result()
        result.entities_in_article = updated.entities_in_article

    return time.monotonic() - t0, sentences
```

**IMPORTANT:** Before implementing this, verify the actual signatures of Preprocessor, Embedder, EntityRecognizer, and CheckWorthinessFilter -- they all extend base classes that take `StreamMessage`, not `NLPResult`. The test harness may have been broken for ALL components, not just BiasDetector. Check each class's `__init__` and `run()` signatures.

---

### Step 6 (Optional): Fix Bug 4 -- Lazy write guard
**File:** `common/models/api/redis_models.py` line 321

**Change:**
```python
# Before
if not self.data.payload.bias_profile and nlp_result.bias_profile:
    self.data.payload.bias_profile = nlp_result.bias_profile

# After
if nlp_result.bias_profile:
    self.data.payload.bias_profile = nlp_result.bias_profile
```

**Risk assessment:** LOW. This only affects reprocessing scenarios. The guard for other fields (claims, entities, sentences) should also be reviewed, but that's out of scope for this plan.

---

## Dependency Graph

```
Step 1   (Bug 1: NameError fix)             -- no dependencies, do first
Step 1.5 (retrieval layer None-guard)       -- no dependencies, do alongside Step 1
Step 2   (Bug 5: lazy init)                 -- no dependencies
Step 3   (Model upgrade)                    -- depends on Step 1 (same file); requires pre-check
Step 4   (Bug 2: test model keys)           -- depends on Step 3 (model name)
Step 5   (Bug 3: test harness)              -- depends on Steps 3, 4
Step 6   (Bug 4: lazy write, optional)      -- independent
```

**Recommended execution:** Steps 1+1.5+2+6 in parallel, then Step 3 pre-check, then Step 3, then Steps 4+5.

---

## Verification Checklist

- [ ] `bias.py`: NameError in except block is gone — test by triggering a classification failure (e.g., empty model)
- [ ] `bias.py`: New model produces `BiasProfile` with `bias_category` in `{Left, Center, Right}`
- [ ] `bias.py`: Sentiment analysis still works unchanged
- [ ] `bias.py`: `_neutral_profile()` is returned and persisted on any inference failure
- [ ] `claimextract.py`: BiasDetector not instantiated when `enable_bias_detection=False`
- [ ] `claimextract.py`: BiasDetector works correctly when `enable_bias_detection=True`
- [ ] `retrieval_service.py`: Processes message with `bias_profile=None` without AttributeError
- [ ] `retrieval_service.py`: Correctly stores DB row with neutral defaults when bias_profile is None
- [ ] `test_components.py`: `--component bias` runs without error
- [ ] `test_components.py`: `--component all` runs without error
- [ ] `manager.py`: `model_manager.load_all(keys=["BIAS_POLITICAL", "BIAS_SENTIMENT"])` succeeds
- [ ] `manager.py`: `_resolve_hf_task` returns `"text-classification"` for BIAS_POLITICAL
- [ ] Dummy mode: NLP service starts correctly with `DUMMY_NLP_MODE=true`
- [ ] No changes to `BiasProfile` dataclass, `StreamMessage` interface, or Redis stream message shapes

---

## Risk Summary

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| New model label IDs differ from expected (0=Left,1=Center,2=Right) | Low | High | Run Step 3 pre-check (`AutoConfig.from_pretrained`) before writing code |
| Retrieval layer crashes on None bias_profile | **CONFIRMED** | **High** | Fixed by Step 1.5 |
| Test harness changes break other components | Medium | Medium | Verify all component `__init__` and `run()` signatures match the dispatch logic |
| Model download fails in CI/Docker | Low | Medium | Model is on HuggingFace with Apache-2.0 license; add to Docker build cache |
| Lazy init adds latency to first bias-enabled article | Low | Low | Model already pre-loaded by ModelManager; BiasDetector init just retrieves it |
