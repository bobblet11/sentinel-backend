# Stats Logging Audit

**Initial audit:** 2026-04-15  
**Re-audited after remote update:** 2026-04-16

## Purpose

This audit reviews the current `stats.json` / log-stat infrastructure used for the project's report, especially the results and analysis sections. It distinguishes between:

- **code state**: what the repository currently implements
- **runtime state**: what the live stats files currently contain

That distinction matters because some code has changed after pulling from remote, while the live log files still contain older or mixed schemas.

## Shared Logging Mechanism

All four processing microservices use `common/io/json_updater.py` via `JsonHandler` to write JSON files under `/app/logs`, protected by a file lock.

## Current Coverage by Service

### Web Scraper

- **Code path:** `microservices/web_scraper/scraper_service.py`
- **Live file:** `logs/scraper/logs/stats.json`
- **Current code records:**
  - jobs processed
  - total, fetch, and parse time
  - HTML and extracted text size
  - min/max fetch and parse times
  - per-outlet stats
  - error counts
- **Runtime state:** mixed schema
  - old top-level summary keys still exist:
    - `total_time_spent_both`
    - `total_jobs_processed`
    - `avg_total_time`
  - newer day entries such as `2026-04-16` are in the new per-day schema

### NLP

- **Code path:** `microservices/nlp/nlp_service.py`
- **Live file:** `logs/nlp/logs/stats.json`
- **Current code records:**
  - jobs processed
  - total claims extracted
  - total entities extracted
  - entity type distribution
  - bias and sentiment category counts
  - per-outlet breakdown
  - error buckets exist in schema
- **Runtime state:** populated and aligned with the current schema

### Retrieval

- **Code path:** `microservices/retrieval_layer/services/retrieval_service.py`
- **Live file:** `logs/retrieval/logs/stats.json`
- **Current code intends to record:**
  - jobs processed
  - input claims evaluated
  - evidence matches
  - verdict distribution
  - confidence score summary
  - related article totals
  - per-outlet breakdown
  - relation buckets declared in schema
- **Runtime state:** still empty (`0` bytes) at time of re-audit

### Ingestor

- **Code path:** `microservices/ingestor/base_ingestor.py`
- **Live files:**
  - `logs/ingestor/stats.json`
  - `logs/ingestor/db_snapshots.json`
- **Current code records:**
  - per-cycle raw fetched count
  - deduplicated count
  - unseen vs seen/skipped count
  - outlet counts
  - cycle duration
  - Redis/Postgres snapshot entries in `db_snapshots.json`
- **Runtime state:**
  - `stats.json` is still old-format only
  - `db_snapshots.json` was not present at time of re-audit

## Live Data Observed on Re-audit

| Service | Live stats file | Observed state |
| --- | --- | --- |
| Scraper | `logs/scraper/logs/stats.json` | Mixed schema: old top-level summary keys plus new day entries |
| NLP | `logs/nlp/logs/stats.json` | Populated, current-format |
| Retrieval | `logs/retrieval/logs/stats.json` | Empty |
| Ingestor | `logs/ingestor/stats.json` | Populated, old-format only |
| Ingestor snapshots | `logs/ingestor/db_snapshots.json` | Missing |

## Status of Previously Identified Issues

### Resolved in code

#### 1. Ingestor snapshot handler mismatch

This was previously reported as:

- `__init__()` created `self.db_snapshot_json_handler`
- `_log_snapshot()` tried to use `self.snapshot_json_handler`

That mismatch is now fixed in code. `_log_snapshot()` currently uses `self.db_snapshot_json_handler`, matching initialization.

- **File:** `microservices/ingestor/base_ingestor.py`
- **Current status:** fixed in repository code
- **Remaining runtime note:** `logs/ingestor/db_snapshots.json` was not yet present during re-audit, so the fix is visible in code but not yet confirmed through fresh runtime output

### Still outstanding

#### 2. Retrieval stats can still crash on empty confidences

`_log_stats()` still calls `max(confidences)` and `min(confidences)` without guarding against an empty list.

- **File:** `microservices/retrieval_layer/services/retrieval_service.py`
- **Impact:** stats logging remains fragile when no confidence values are produced

#### 3. Retrieval average confidence is still incorrect

The code still does:

- `sum += sum(confidences)`
- `count += 1`

That means the implied average is per-job, not per-confidence value.

- **File:** `microservices/retrieval_layer/services/retrieval_service.py`
- **Impact:** average confidence derived from stats is misleading

#### 4. Retrieval relation buckets are still declared but never populated

The schema still contains:

```json
"relations": {"support": 0, "contradict": 0, "irrelevant": 0}
```

but `_log_stats()` still does not update those counters.

- **File:** `microservices/retrieval_layer/services/retrieval_service.py`
- **Impact:** useful report data is structurally present but operationally absent

#### 5. NLP errors are still not categorized in stats

`nlp_service.py` still defines `error_type` in `_log_stats()`, but the exception path still calls `_log_stats()` without passing it.

- **File:** `microservices/nlp/nlp_service.py`
- **Impact:** `errors` remains empty even when NLP processing fails

#### 6. Scraper schema compatibility is still not handled explicitly

The code still uses `setdefault(day_key, {...})` with no migration/reset logic for older entries. The runtime file now shows that the system has partially moved forward:

- old top-level summary keys remain
- newer day entries are being written in the new schema

So the live file is now **mixed-format**, not purely old-format. That is an improvement over the earlier observation, but schema normalization is still missing.

- **File:** `microservices/web_scraper/scraper_service.py`
- **Impact:** report tooling must handle mixed scraper schema carefully

#### 7. Ingestor runtime data is still legacy-format

The ingestor code now writes per-cycle timestamp keys such as:

- `raw_total`
- `deduplicated_total`
- `unseen`
- `seen_skipped`
- `outlet_counts`
- `cycle_duration_s`

However, the live `logs/ingestor/stats.json` still contains only older daily aggregate keys:

- `newly_added_urls`
- `already_seen_urls`
- `total_urls_processed`
- `cycles`

- **File:** `microservices/ingestor/base_ingestor.py`
- **Impact:** runtime data has not yet caught up to current code

## Additional Findings from Re-audit

### Scraper is now actively writing the new daily schema

This is the biggest runtime change since the initial audit. The scraper file is no longer purely old-format. It now contains:

- legacy top-level summary keys from the older format
- newer date keys like `2026-04-16` using the current per-day structure

This means the migration is partially happening in practice, but the file is still not normalized.

### Retrieval logging still appears inactive in runtime

`logs/retrieval/logs/stats.json` remains empty even though retrieval logging code exists. That suggests one of:

1. retrieval has not processed fresh work since the last reset
2. retrieval logging is not being reached
3. retrieval logging is failing before persisting

For report generation, retrieval stats should not be treated as available until live data appears.

## Existing Stats Already Useful for the Report

### Scraper

- fetch and parse latency
- min/max timing
- per-outlet article processing
- HTML vs extracted text size
- error counts by outlet

### NLP

- claims extracted
- entity distribution
- bias category distribution
- sentiment category distribution
- per-outlet NLP output volume

### Retrieval

- verdict distribution
- number of evidence matches
- related article count

These are useful in code design, but currently unavailable in runtime because the live retrieval stats file is empty.

### Ingestor

- raw vs deduplicated article counts
- unseen vs already-seen counts
- per-cycle or per-day ingestion volume, depending on schema

## Recommended New Stats

These additions would strengthen the results and analysis section of the report.

### High value

#### 1. NLP processing time per article

NLP still has no timing metrics.

Recommended fields:

- `total_processing_time_s`
- `min_processing_time_s`
- `max_processing_time_s`
- per-outlet total processing time

#### 2. Retrieval processing time per article

Retrieval still lacks latency metrics.

Recommended fields:

- `total_processing_time_s`
- `min_processing_time_s`
- `max_processing_time_s`

### Medium value

#### 3. NLP bias confidence distribution

NLP records category counts but not confidence strength.

Recommended fields:

- `bias_confidence_sum`
- `bias_confidence_count`
- optional min/max confidence

#### 4. Claims-per-article distribution

Current NLP stats expose only totals, not distribution shape.

Recommended fields:

- `min_claims_per_article`
- `max_claims_per_article`
- average derived from total claims / jobs

#### 5. Retrieval relation distribution

The schema already suggests this metric; it only needs to be wired up.

Recommended fields:

- `support`
- `contradict`
- `irrelevant`

### Lower value but still useful

#### 6. Ingestor per-outlet new vs seen breakdown

The ingestor currently logs outlet totals, but not freshness per outlet.

Recommended fields:

- `outlet_new_counts`
- `outlet_seen_counts`

## Updated Priority

1. Fix retrieval empty-confidence crash
2. Fix retrieval confidence averaging semantics
3. Populate retrieval relation buckets
4. Pass NLP `error_type` on exception paths
5. Normalize scraper mixed schema
6. Confirm ingestor snapshot file generation in runtime
7. Add NLP timing stats
8. Add retrieval timing stats
9. Add NLP confidence and claim-distribution stats
10. Migrate or reset legacy ingestor stats data

## Notes for Report Writing

- The codebase has improved since the initial audit: the ingestor snapshot handler mismatch is now fixed in code.
- The runtime logging state is still uneven:
  - scraper is mixed-format
  - NLP is usable
  - retrieval is empty
  - ingestor still reflects older runtime data
- For the report, **NLP and scraper currently provide the most usable live stats**.
- Retrieval and ingestor data should be treated carefully until fresh runtime output confirms the current code paths are actually producing the expected files and schema.
