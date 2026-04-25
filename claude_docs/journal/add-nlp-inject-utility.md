---
## [2026-04-02 00:00] Create NLP Stream Injection Test Utility

**Date**: April 2, 2026 at 2:20 PM UTC
**Agent**: `claude-inline`
**Branch**: `newretrieval-fixes`
**Triggered By**: Developer request to allow direct injection of article payloads into the NLP service Redis input stream without needing the API or web scraper services running.

### Summary
Created a standalone developer utility script (`microservices/nlp/tests/inject_to_nlp.py`) that reads an article JSON file from the `debug_articles/` directory and publishes it directly to the `user:to.be.nlp` Redis stream using the exact `{"payload": json.dumps(...)}` envelope format that `RedisPublisher` uses. This allows isolated NLP service testing without any upstream service dependencies.

### Files Changed
| File Path | Change Type | Description |
|-----------|-------------|-------------|
| `microservices/nlp/tests/inject_to_nlp.py` | Created | Developer utility that reads a debug article JSON, builds a complete `Message`/`MessageHeader`/`MessagePayload` structure (with generated UUID and UTC timestamp), and publishes it to the NLP input stream via `redis.xadd`. Targets `user:to.be.nlp` on `localhost:6379` by default; overridable via `NLP_INPUT_STREAM`, `REDIS_HOST`, and `REDIS_PORT` env vars. A `file` variable at the top of the script is the single configuration point for selecting which article to inject. |

### Details
- The script constructs a message envelope matching the `Message` Pydantic schema: a `header` dict (uid, type, status, created_at) and a `payload` dict (article_url, news_outlet, title, parsed_text, summary).
- Field mapping handles both naming conventions present in debug article JSON files: `article_url`/`url`, `news_outlet`/`source`, `article_title`→`title`, `article_text`→`parsed_text`.
- On success, prints the Redis stream entry ID, the generated job UID, title, outlet, and URL for traceability.
- Performs a `ping()` before publishing; exits with a clear error message if Redis is unreachable.
- Default article target: `microservices/nlp/tests/debug_articles/bbc_001.json`.
- No new dependencies — uses the `redis` package already present in the NLP service environment.
- This is a developer tool only; it is not invoked by any pipeline service or test runner.

### Pipeline Impact
None — this is a test utility script that lives under `tests/` and is not imported by any service or automated test suite. It does not modify any stream interface, schema, or service logic. E2E stability is unaffected.

---
