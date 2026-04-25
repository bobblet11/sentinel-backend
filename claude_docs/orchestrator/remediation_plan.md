# Remediation Plan: Align nlp_service.py with Test Script Pipeline Model

## Status: EXECUTED
## Created: 2026-03-26T00:00:00Z
## Branch: refactor/nlp

## Problem Statement

`nlp_service.py` delegates all pipeline work to a monolithic `ClaimExtraction` orchestrator (`claimextract.py`) which:
- Uses an 8-stage pipeline with extra components (`SentenceExtraction`, `Decontextualizer`, entity mapping, Sentence-to-Claim conversion) not present in the test scripts
- Has a different pipeline order than the test scripts
- Hides sentence flow inside the orchestrator rather than using typed dispatch

The test scripts (`run_pipeline_tests.py` and `test_components.py`) define the authoritative pipeline:

```
Preprocessor (SentenceGenerator) -> Embedder (SentenceProcessor) -> BiasDetector (ArticleProcessor) -> EntityRecognizer (SentenceConsumer) -> CheckWorthinessFilter (SentenceProcessor)
```

## Changes Required

### File: `microservices/nlp/nlp_service.py`

**Change 1: Replace imports**
- Remove: `from microservices.nlp.components.claimextract import ClaimExtraction`
- Add:
  ```python
  from microservices.nlp.components.preprocess import Preprocessor
  from microservices.nlp.components.embedder import Embedder
  from microservices.nlp.components.bias import BiasDetector
  from microservices.nlp.components.ner import EntityRecognizer
  from microservices.nlp.components.checkworthy import CheckWorthinessFilter
  ```

**Change 2: Define PIPELINE_ORDER constant**
Add after the `EMBEDDING_DIM` constant:
```python
PIPELINE_ORDER = [
    ("Preprocessor", Preprocessor, "SentenceGenerator"),
    ("Embedder", Embedder, "SentenceProcessor"),
    ("BiasDetector", BiasDetector, "ArticleProcessor"),
    ("EntityRecognizer", EntityRecognizer, "SentenceConsumer"),
    ("CheckWorthinessFilter", CheckWorthinessFilter, "SentenceProcessor"),
]
```

**Change 3: Update `__init__` to build flat component list**
Replace the `else` branch (lines 80-90) that creates `ClaimExtraction` with:
```python
else:
    model_manager.load_all()
    self.pipeline = [
        (name, cls(), ctype) for name, cls, ctype in PIPELINE_ORDER
    ]
    logger.info("Model health: %s", model_manager.health_check())
```
For dummy mode, keep `self.pipeline = []` but type it as a list of tuples.

**Change 4: Rewrite `_analyze_html_and_update` with typed dispatch**
Replace the existing loop (lines 99-114) with dispatch logic matching the test scripts:
```python
def _analyze_html_and_update(self, message: StreamMessage) -> StreamMessage:
    article = Article(text=message.text, title=message.title, link=message.link)
    result = NLPResult()
    sentences: List[SentenceScore] = []

    for name, component, component_type in self.pipeline:
        try:
            if component_type == "SentenceGenerator":
                sentences = component.run(article, result, self.options)
            elif component_type == "SentenceProcessor":
                sentences = component.run(article, result, self.options, sentences)
            elif component_type == "SentenceConsumer":
                component.run(article, result, self.options, sentences)
            else:  # ArticleProcessor
                component.run(article, result, self.options)
        except torch.cuda.OutOfMemoryError as oom:
            logger.error(
                "CUDA OOM in %s: %s. Flushing cache and aborting article.",
                name, oom,
            )
            torch.cuda.empty_cache()
            raise
        except Exception as e:
            logger.error("Pipeline error in %s: %s", name, e)
            raise

    result.sentences = sentences
    message.set_nlp_result(result)
    return message
```

**Change 5: Add SentenceScore import**
Add `SentenceScore` to the imports from `common.models.api.redis_models`.

### Files NOT to modify
- `microservices/nlp/components/claimextract.py` -- leave as-is (may be useful for future reference or alternative pipeline modes)
- `microservices/nlp/tests/debug_articles/run_pipeline_tests.py` -- source of truth, do not touch
- `microservices/nlp/tests/debug_articles/test_components.py` -- source of truth, do not touch
- Individual component files -- their signatures are already correct

### Verification
After changes, confirm:
1. `nlp_service.py` imports no longer reference `ClaimExtraction`
2. The pipeline order matches: Preprocessor -> Embedder -> BiasDetector -> EntityRecognizer -> CheckWorthinessFilter
3. Typed dispatch uses the same 4 branches as the test scripts
4. `SentenceScore` is imported
5. Dummy mode still works (empty pipeline, dummy result)
6. `result.sentences = sentences` is set before `set_nlp_result` (preserves downstream compatibility)
