# Sentinel Backend Workspace Instructions

## Operating Principles
- Preserve end-to-end pipeline stability: scrape -> NLP -> retrieval -> API.
- Respect service boundaries and shared contracts. Do not change stream payloads or shared models without updating all consumers.
- Prefer explicit boundary logging patterns from [common/io/logging.py](../common/io/logging.py).
- Keep NLP and scraper dummy modes working for local development.
- Store project analysis/workflow markdown under [claude_docs/](../claude_docs/), not at repository root.

For full safeguards and agent routing rules, see [CLAUDE.md](../CLAUDE.md).

## Commands Agents Should Use
- Deploy: `./scripts/deploy.sh [base|nlptest|benchmark-1]`
- Clean containers: `./scripts/clean.sh [base|nlptest|benchmark-1]`
- Clear persisted data: `./scripts/clear_data.sh`
- Format and lint: `./scripts/format_and_lint.sh`
- Tests: `pytest tests/` or `pytest tests/sprint4/`

If command behavior appears inconsistent, verify scripts in [scripts/](../scripts/) and current guidance in [CLAUDE.md](../CLAUDE.md).

## Architecture Boundaries
- Inter-service async communication is via Redis Streams with user/background priority lanes.
- Common stream pattern is `{job_type}:to.be.{stage}` plus failure streams.
- Shared DTO/ORM contracts live under [common/models/](../common/models/).
- Core service lifecycle behavior is centralized in [common/service/service_template.py](../common/service/service_template.py).

Before touching interfaces, map all downstream consumers across API, scraper, NLP, and retrieval services.

## Project-Specific Conventions
- Keep API DTOs and database models aligned with existing Pydantic/SQLAlchemy patterns in [common/models/](../common/models/).
- NLP pipeline changes must preserve component I/O contracts and ordering expectations in [microservices/nlp/](../microservices/nlp/).
- Prefer existing retry/redis utilities from [common/redis_client/](../common/redis_client/) over custom stream logic.
- Keep lint/type compatibility with [mypy.ini](../mypy.ini) and `format_and_lint.sh` settings.

## Documentation: Link, Do Not Duplicate
- Setup and environment details: [README.md](../README.md)
- Pipeline safeguards and architecture context: [CLAUDE.md](../CLAUDE.md)
- Current API behavior/status snapshot: [BACKEND_STATUS.md](../BACKEND_STATUS.md)
- Example response shape: [expected_response.md](../expected_response.md)

Use these docs as the source of truth; keep new instructions concise and reference-first.

<claude-mem-context>
# claude-mem: Cross-Session Memory

*No context yet. Complete your first session and context will appear here.*

Use claude-mem's MCP search tools for manual memory queries.
</claude-mem-context>
