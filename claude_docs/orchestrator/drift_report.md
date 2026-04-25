# Drift Report: NLP Pipeline Alignment

## Date: 2026-03-26
## Branch: refactor/nlp

## Detected Inconsistencies (RESOLVED)

### 1. Pipeline Architecture Mismatch (FIXED)

**Before**: `nlp_service.py` delegated all pipeline work to a monolithic `ClaimExtraction` orchestrator that ran an 8-stage pipeline internally:
```
Preprocessor -> EntityRecognizer -> SentenceExtraction -> Decontextualizer ->
CheckWorthinessFilter -> EntityMapping -> Embedder -> Sentence-to-Claim -> BiasDetector
```

**After**: `nlp_service.py` now uses flat component dispatch matching the test scripts:
```
Preprocessor -> Embedder -> BiasDetector -> EntityRecognizer -> CheckWorthinessFilter
```

### 2. Extra Components Removed from Service Layer

`SentenceExtraction` and `Decontextualizer` were stages in `ClaimExtraction` that are not present in the test script pipeline. The inline Sentence-to-Claim conversion and EntityMapping steps were also removed from the service path.

Note: `claimextract.py` was NOT deleted -- it remains as a reference implementation and could

 be used for alternative pipeline configurations in the future.

### 3. Typed Dispatch Adopted

**Before**: `nlp_service.py` iterated a `List[ArticleProcessor]` and called `component.run(article, result, options)` with a uniform 3-arg signature.

**After**: Uses typed dispatch with 4 branches matching the test scripts:
- `SentenceGenerator` -- `run(article, result, options) -> List[SentenceScore]`
- `SentenceProcessor` -- `run(article, result, options, sentences) -> List[SentenceScore]`
- `SentenceConsumer` -- `run(article, result, options, sentences) -> None`
- `ArticleProcessor` -- `run(article, result, options) -> None`

## Remaining Observations (NOT inconsistencies, but worth noting)

### Base Class Misalignment in Component Files

Two components have `run()` signatures that do not match their declared base class:

1. **Preprocessor** extends `SentenceProcessor` (which declares `run(article, result, options, sentences) -> List[SentenceScore]`), but its actual `run()` takes only 3 args `(article, result, options)`. The test scripts treat it as `SentenceGenerator`, which is a type tag -- there is no `SentenceGenerator` ABC in `models/base.py`.

2. **EntityRecognizer** extends `ArticleProcessor` (which declares `run(article, result, options) -> None`), but its actual `run()` takes 4 args `(article, result, options, sentences)`. The test scripts treat it as `SentenceConsumer`, which is also a type tag with no corresponding ABC.

These work at runtime because Python does not enforce abstract method signature matching, and the typed dispatch in both `nlp_service.py` and the test scripts calls them with the correct number of arguments. However, the base class contracts are technically violated.

**Recommendation**: Consider adding `SentenceGenerator` and `SentenceConsumer` ABCs to `models/base.py` and updating `Preprocessor` and `EntityRecognizer` to inherit from the correct one. This is a low-priority cleanup.

### CheckWorthinessFilter Builds Claims

`CheckWorthinessFilter.run()` writes `result.claims_in_article` directly (lines 103-115 of `checkworthy.py`). This means claims are built during the final pipeline stage without needing a separate Sentence-to-Claim conversion step. This is consistent with the test script model.
