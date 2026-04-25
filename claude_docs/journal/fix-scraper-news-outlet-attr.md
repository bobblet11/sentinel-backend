---
name: Fix AttributeError on message.news_outlet in scraper debug log
description: Corrects wrong StreamMessage attribute name in scraper_service.py debug log statement
type: fix
agent: claude-inline
branch: newretrieval-fixes
date: 2026-04-02
---

## Fix AttributeError on `message.news_outlet` in Scraper Debug Log

**Date**: April 2, 2026 at 4:45 PM UTC
**Agent**: `claude-inline`
**Branch**: `newretrieval-fixes`
**Triggered By**: Bug fix — scraper crashed with AttributeError at DEBUG log level due to a non-existent attribute access on `StreamMessage`.

### Summary
`scraper_service.py` line 215 referenced `message.news_outlet`, which does not exist on `StreamMessage`. The correct property is `news_outlet_name`, defined in `common/models/api/redis_models.py` (line 252). Because the bad attribute access was inside a `self.logger.debug(...)` call, the crash was invisible at INFO level and only manifested when `LOG_MODE=10` (DEBUG).

### Files Changed
| File Path | Change Type | Description |
|-----------|-------------|-------------|
| `microservices/web_scraper/scraper_service.py` | Modified | Line 215: `message.news_outlet` → `message.news_outlet_name` |

### Details
- `StreamMessage.news_outlet_name` is a `@property` in `common/models/api/redis_models.py:252`; no `news_outlet` attribute exists on the model.
- Python evaluates `logger.debug()` arguments before passing them, so the AttributeError is raised and crashes the worker even when DEBUG output would be suppressed — but only when a DEBUG handler is active (`LOG_MODE=10`).
- No interface, schema, or downstream service changes. Pure attribute-name correction in a log statement.

### Pipeline Impact
Scraper stage only. Eliminates fatal worker crash at `LOG_MODE=10`. E2E stability at INFO level was never affected.
