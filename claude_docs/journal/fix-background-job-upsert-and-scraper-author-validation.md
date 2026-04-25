---
## [2026-04-17 13:29] Upsert Background Jobs for Fast-Path Retrieval and Allow Missing Authors

**Date**: April 17, 2026 at 1:29 PM UTC
**Agent**: `plan-executor`
**Branch**: `main`
**Triggered By**: User-requested plan execution to make background-analyzed articles fast-path eligible and stop rejecting otherwise valid scraper output when author extraction fails.

### Summary
The retrieval layer now upserts and completes dedicated background job rows keyed by uid so background-analyzed articles can become eligible for API fast-path retrieval. The scraper validation helper was also relaxed to allow `author=None`, preventing valid articles from being dropped solely because author extraction failed.

### Files Changed
| File Path | Change Type | Description |
|-----------|-------------|-------------|
| `microservices/retrieval_layer/storage/dtos.py` | Modified | Added an `UpsertBackgroundJob` DTO for background job persistence. |
| `microservices/retrieval_layer/storage/crud.py` | Modified | Added a background-job upsert helper keyed by uid that reuses same-uid rows, marks them complete, fills only missing timestamps, and raises if a uid resolves to a different `article_id`. |
| `microservices/retrieval_layer/services/retrieval_service.py` | Modified | Switched background message handling to persist and complete its own background job row after saving article data, and wrote the resolved database job id back into `message.data.header.id`. |
| `common/models/api/validation_helpers.py` | Modified | Removed the hard requirement that scraper payloads include an author value. |
| `tests/test_retrieval_background_job_upsert.py` | Created | Added targeted coverage for background job row creation and idempotent retry behavior. |
| `tests/test_webscraper_validation_helpers.py` | Created | Added targeted coverage proving `author=None` is accepted while the remaining validation guardrails still apply. |

### Details
- Background retrieval messages no longer depend on the user-job completion path; they now create or reuse their own completed background job record after the article save succeeds.
- The upsert path is defensive: it preserves existing timestamps where present, only fills missing values, and fails fast if the same uid is associated with a different article.
- Existing older articles processed before this fix may still lack completed background job rows and will need reprocessing or a backfill before they become fast-path eligible.
- The previously applied fast-path commit-order fix in `microservices/api/app/api/v1/endpoints/jobs.py` was intentionally left unchanged.

### Pipeline Impact
- **Retrieval**: High impact — background-processed articles can now surface through the API fast path because a completed background job row exists.
- **Scrape / validation**: Medium impact — scraper output with no extracted author is no longer rejected if other required fields are valid.
- **API**: Indirect impact only through improved fast-path eligibility; the endpoint commit-order logic was not modified in this task.
- E2E stability was not verified in this journal step; coverage added was targeted unit-level regression testing.

---
