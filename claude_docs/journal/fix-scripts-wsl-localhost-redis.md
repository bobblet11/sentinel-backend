---
## [2026-04-17 00:00] Fix Scripts to Use localhost for Redis When Run from WSL

**Date**: April 17, 2026 at 12:00 AM UTC
**Agent**: `claude-inline`
**Branch**: `main`
**Triggered By**: Inline fix to allow `inspect_aws.py` and `skip_to_newer.py` to connect to Redis when run directly from WSL where the SSH tunnel is bound to `localhost:16379`.

### Summary
Both scripts defaulted to `host.docker.internal` as the Redis host, which resolves correctly inside Docker containers but not from a WSL shell. When running these scripts directly in WSL, the SSH tunnel to ElastiCache/Redis is bound to `localhost`, so the host override was added to redirect connections accordingly.

### Files Changed
| File Path | Change Type | Description |
|-----------|-------------|-------------|
| `scripts/database/inspect_aws.py` | Modified | After `load_dotenv`, added an override: if `REDIS_HOST == "host.docker.internal"`, set it to `"localhost"` before importing `redis_connection`. |
| `scripts/redis_cli/skip_to_newer.py` | Modified | Changed the default value for `REDIS_HOST` in `get_redis_connection()` from `"host.docker.internal"` to `"localhost"`. |

### Details
- `host.docker.internal` is a Docker-internal DNS alias for the container host; it is not resolvable in a plain WSL environment.
- The SSH tunnel for ElastiCache access is typically established as `localhost:16379 → <elasticache-endpoint>:6379`.
- `inspect_aws.py` reads `REDIS_HOST` from the environment (via `.env`), so the fix adds a post-load override rather than changing the `.env` template.
- `skip_to_newer.py` uses a local default argument, so changing the default directly is sufficient.
- No changes to shared library code or stream interfaces.

### Pipeline Impact
None — these are standalone admin/debug scripts, not part of the live pipeline. No E2E impact.

---
