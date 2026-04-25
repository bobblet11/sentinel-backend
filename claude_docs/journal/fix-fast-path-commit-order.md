---
## [2026-04-17 12:28] Finalize fast-path commit-before-publish race fix

**Date**: April 17, 2026 at 12:28 PM UTC
**Agent**: `claude-inline`
**Branch**: `main`
**Triggered By**: Record the final inline journal entry for the fast-path race-condition fix on the current branch

### Summary
The fast-path branch for background-analysed articles now commits the new job row before publishing to retrieval, fixing the verified race where retrieval could consume a message before the API transaction made the job visible. The patch remains intentionally narrow: only the fast-path branch changed, the regression test was simplified into a dependency-free AST/unittest guard, and the active plan was updated to reflect the reduced scope.

### Files Changed
| File Path | Change Type | Description |
|-----------|-------------|-------------|
| `microservices/api/app/api/v1/endpoints/jobs.py` | Modified | Moved the fast-path `db.commit()` ahead of `publish_job_to_retrieval()` so retrieval cannot read an uncommitted user job |
| `tests/test_fast_path_commit_order.py` | Created | Reworked the regression coverage into a dependency-free `unittest`/AST check that asserts `db.commit` happens before `publish_job_to_retrieval` in the fast-path branch |
| `/home/farhan/.copilot/session-state/34c7fd35-5e27-4808-9af1-ea9cff8c4b49/plan.md` | Modified | Updated the session plan to document the narrowed fast-path-only scope and current execution status |

### Details
- The fix is scoped only to the background-job fast path in `submit_job`; the fresh-article and retry flows were left unchanged to minimize regression risk.
- The new regression test parses `jobs.py` directly and inspects the fast-path branch call order without importing API dependencies.
- The plan now reflects that only the verified commit-ordering race was addressed in this pass, while other identified issues remain out of scope.

### Pipeline Impact
API and retrieval handoff affected. This hardens the fast-path transition into retrieval for already-analysed articles by ensuring the job row is committed before publish; scrape, NLP, fresh-article, and retry flows were intentionally left untouched. E2E stability was not verified here; validation is limited to the focused AST regression test.

---

---
## [2026-04-17 12:23] Commit fast-path jobs before retrieval publish

**Date**: April 17, 2026 at 12:23 PM UTC
**Agent**: `claude-inline`
**Branch**: `main`
**Triggered By**: Fix a verified fast-path race condition and record the inline API/test/plan updates

### Summary
The fast-path user-job branch in the jobs endpoint now commits the newly created job row before publishing to `user:to.be.retrieval`, closing the race where retrieval could consume the message before the job existed in PostgreSQL. A focused regression test was added to lock in the commit-before-publish ordering, and the session plan was narrowed to reflect the scoped fix.

### Files Changed
| File Path | Change Type | Description |
|-----------|-------------|-------------|
| `microservices/api/app/api/v1/endpoints/jobs.py` | Modified | Moved the fast-path `db.commit()` ahead of `publish_job_to_retrieval()` so retrieval cannot observe an uncommitted user job |
| `tests/test_fast_path_commit_order.py` | Created | Added a focused regression test asserting the fast-path branch calls `commit` before `publish_job_to_retrieval` |
| `/home/farhan/.copilot/session-state/34c7fd35-5e27-4808-9af1-ea9cff8c4b49/plan.md` | Modified | Updated the active session plan to document the narrowed scope and current execution state for this fix |

### Details
- The change is intentionally limited to the fast-path branch that reuses an already-processed article for a user job.
- The retry and fresh-article publish paths were left unchanged to minimize regression risk in the broader submission flow.
- The added regression test stubs the endpoint dependencies and verifies the exact call order: `create_job` → `commit` → `publish`.
- The session plan still documents other identified issues, but its execution update now reflects that only the fast-path ordering fix was implemented in this pass.

### Pipeline Impact
API and retrieval handoff affected. This change hardens the fast-path transition into `user:to.be.retrieval` by ensuring the job row is durable before retrieval can consume it; the normal scrape/NLP path was intentionally left untouched. E2E pipeline stability was not verified here; coverage is limited to the focused regression test.

---
