# Plan: Fix Retrieval Layer — Claims Returning Zero Matches

## Context

The retrieval layer's 3-stage pipeline (symbolic filter → embedding similarity → NLI) is returning almost no matching claims for extracted claims, even with a large database. Investigation found 3 compounding bugs that together cause near-zero recall.

---

## Root Causes

### Bug 1 (Critical): No fallback when symbolic filter returns empty

**File:** `microservices/retrieval_layer/services/retrieval_service.py:317-318`

`filter_step()` returns `[]` immediately if keyword and entity searches find no candidates:

```python
if not claim_candidates:
    return []
```

When this happens, `similarity_step()` never runs at all — not even a full embedding scan. Any claim that doesn't keyword-match an article title AND has no NER entities in the DB returns 0 results, regardless of how semantically similar DB content is.

The unused `pipeline.py` (`MIN_SIMILARITY=0.25`) correctly falls back to `retrieve_by_embedding(candidate_claim_ids=[])` which triggers a full scan. `retrieval_service.py` never does this.

---

### Bug 2 (High): MIN_SIMILARITY = 0.7 is far too strict

**File:** `microservices/retrieval_layer/services/retrieval_service.py:41`

Cosine similarity 0.7 means vectors must be within ~45° of each other — very strict for cross-article claim matching with differently-worded sentences. The unused `pipeline.py` uses 0.25. A value around **0.35** is more appropriate for this use case.

---

### Bug 3 (High): Date filter ±30 days eliminates most of the DB

**File:** `microservices/retrieval_layer/services/retrieval_service.py:292-293`

The symbolic filter restricts candidates to articles published within ±30 days of the input article. For fact-checking, evidence can legitimately come from articles published months or years apart. This kills most of the candidate pool before the embedding step.

---

### Bug 4 (Secondary): `retrieve_by_embedding_full_scan` missing fields in result dict

**File:** `microservices/retrieval_layer/retrieval/embedding_retriever.py:106-113`

The full scan result dict only includes `id` and `decontextualised_claim` — missing `article_id`, `source_url`, `source_excerpt`. Once the fallback is enabled, downstream code in `retrieval_service.py` will access these fields and get `None`, causing the article-exclusion filter at line 387 to fail silently and missing source info in results.

Also, `retrieve_by_embedding_full_scan` has no `exclude_article_id` param — it must be added so the original article's own claims aren't returned as evidence.

---

## Changes

### 1. Fix `retrieve_by_embedding_full_scan` — add missing fields + `exclude_article_id`

**File:** `microservices/retrieval_layer/retrieval/embedding_retriever.py`

- Add `exclude_article_id: int | None = None` parameter
- Join `Article` table in the full scan query (same as the candidate-filtered query)
- Include `article_id`, `url`, `source_excerpt` in the result dict
- Apply `exclude_article_id` filter in WHERE clause

---

### 2. Fix `retrieve_by_embedding` — pass `exclude_article_id` to full scan

**File:** `microservices/retrieval_layer/retrieval/embedding_retriever.py:32-38`

Add `exclude_article_id` to the `retrieve_by_embedding_full_scan(...)` call when falling back.

---

### 3. Fix `filter_step` — remove the early return, pass empty list to similarity step

**File:** `microservices/retrieval_layer/services/retrieval_service.py:317-323`

Remove:
```python
if not claim_candidates:
    return []
```

Return `[]` (empty candidate list) instead — `similarity_step` passes this to `retrieve_by_embedding`, which already handles the empty case by falling through to `retrieve_by_embedding_full_scan`.

---

### 4. Lower MIN_SIMILARITY from 0.7 → 0.35

**File:** `microservices/retrieval_layer/services/retrieval_service.py:41`

```python
MIN_SIMILARITY = 0.35
```

---

### 5. Remove (or greatly relax) the date filter

**File:** `microservices/retrieval_layer/services/retrieval_service.py:287-295`

Remove the `published_after` / `published_before` date window from the keyword and entity filter calls. These filters are fine for narrowing noisy results but should not be used when the DB is not yet large enough to warrant temporal filtering. Remove the filter entirely for now. The `publish_date` parsing block can remain but the computed values simply won't be passed to the filter functions.

---

## Critical Files

| File | Lines | Change |
|---|---|---|
| `microservices/retrieval_layer/retrieval/embedding_retriever.py` | 81-115 | Fix full scan: add `exclude_article_id`, join `Article`, include missing fields |
| `microservices/retrieval_layer/retrieval/embedding_retriever.py` | 32-38 | Pass `exclude_article_id` to full scan fallback |
| `microservices/retrieval_layer/services/retrieval_service.py` | 317-323 | Remove early `return []` in `filter_step` |
| `microservices/retrieval_layer/services/retrieval_service.py` | 41 | Lower `MIN_SIMILARITY` to 0.35 |
| `microservices/retrieval_layer/services/retrieval_service.py` | 297-314 | Remove `published_after`/`published_before` from filter calls |

---

## Verification

1. Run a user job through the pipeline and check the retrieval result hash in Redis — `matches` array should now be non-empty for most claims with DB content.
2. Check `stats.json` inside the retrieval container — `evidence_matches` count should increase and "unverified" verdict rate should drop.
3. Confirm no regression: the `article_id` exclusion filter still works (results don't include claims from the same article).
4. Run `pytest tests/` to check no unit test regressions.
