---
date: 2026-04-06
agent: claude-inline
branch: newretrieval-fixes
files_changed:
  - microservices/ingestor/base_ingestor.py
---

## What changed

Fixed a `NameError` in `base_ingestor.py:_log_stats()` where 3 references used the undefined variable `data` instead of `file_data`.

- Line 81: `sorted(data.keys())` → `sorted(file_data.keys())`
- Line 84: `del data[old_date]` → `del file_data[old_date]`
- Line 89: `write_json(data)` → `write_json(file_data)`

## Why

The ingestor was crashing after every successful run with `NameError: name 'data' is not defined`. The method read stats into `file_data` at line 61 but the pruning and persist block (lines 81–89) incorrectly referenced `data`. Ingestion itself completed fine (messages published to Redis) but the post-run stats logging always crashed the process.

## Impact

Ingestor no longer crashes after each cycle. `stats.json` will now be correctly updated and pruned to 30 days.
