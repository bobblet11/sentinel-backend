# AGENTS.md — Sentinel Backend

Guidance for agentic coding agents operating in this repository.
See also: `CLAUDE.md` (safeguards + agent routing), `claude_docs/INDEX.md`.

---

## Agent Routing (Do This First)

Before working inline, check whether a specialist agent fits the task:

| Agent | Use when |
|---|---|
| `systems-planner` | Any change touching >1 service or a shared interface |
| `plan-executor` | Executing a plan already stored in `claude_docs/` |
| `sentinel-orchestrator` | Syncing project state or auditing agent configs after major refactors |
| `explore` | Fast codebase searches: find files, grep keywords, answer structural questions |

**Rule**: If the task touches more than one service, modifies a shared interface, or requires planning — invoke `systems-planner` first.

---

## Build / Deploy Commands

```bash
# First-time setup
cp configs/.env.template configs/.env

# Deploy all services (CONFIG_NAME: base | nlptest | benchmark-1)
./scripts/deploy.sh [CONFIG_NAME]

# Stop and remove containers
./scripts/clean.sh [CONFIG_NAME]

# Wipe PostgreSQL and Redis data
./scripts/clear_data.sh

# Hard reset (removes all containers + data)
./scripts/nuke_clean.sh

# View service logs
./scripts/logs.sh <service_name>
```

Run services locally without Docker:
```bash
python -m microservices.api.app.main
python -m microservices.nlp.main
python -m microservices.web_scraper.main
python -m microservices.ingestor.main
python -m microservices.retrieval_layer.main
```

---

## Lint / Format Commands

```bash
# Full pipeline: autoflake → isort → black → flake8 → mypy
./scripts/format_and_lint.sh

# Run tools individually
autoflake --in-place --recursive --remove-all-unused-imports --remove-unused-variables .
isort .
black .                             # line length 88
flake8 . --max-line-length=88 --ignore=E501,E203,W503
mypy .                              # config in mypy.ini
```

Excluded from all lint/format: paths matching `**/cronjob`.
mypy config is in `mypy.ini`; `feedparser` stubs are ignored project-wide.

---

## Test Commands

```bash
# Run all tests
pytest tests/

# Run a specific test file
pytest tests/benchmarks/benchmark_1_1.py

# Run a single test by name
pytest tests/benchmarks/benchmark_1_1.py::Benchmark_1_1::execute

# Verbose output
pytest tests/ -v

# Stop on first failure
pytest tests/ -x
```

Tests live under `tests/benchmarks/`. There is no `conftest.py`; each module is self-contained.
After significant changes, verify the full pipeline manually:
`POST /api/v1/jobs` → poll `GET /api/v1/jobs/{uuid}/result`.

---

## Code Style

### Language & Versions
- Python **3.11 / 3.12** (each service picks one; check its `Dockerfile`).
- FastAPI for HTTP; SQLAlchemy (sync) for ORM; Pydantic **v2** for validation.

### Formatting
- `black` — line length **88**. No manual line-wrapping needed.
- `isort` — import sorting; always run before `black`.
- `autoflake` — removes unused imports and variables; run first.

### Type Hints
- **Mandatory** on all new functions, methods, and class attributes.
- Use `from __future__ import annotations` only when needed for forward refs.
- Prefer `X | None` over `Optional[X]` in new code (both exist in the codebase).
- Use `List`, `Dict`, `Tuple` from `typing` for Python 3.11 compat; `list[X]` / `dict[K, V]` is fine in 3.12-only code.

### Imports Order (enforced by isort)
1. Standard library
2. Third-party packages
3. `common.*` shared library
4. Intra-service imports (`microservices.<service>.*`)

```python
import logging
from typing import List, Optional

from pydantic import BaseModel

from common.models.api.redis_models import StreamMessage
from microservices.nlp.config import DUMMY_NLP_MODE
```

### Naming Conventions
- **Modules / packages**: `snake_case`
- **Classes**: `PascalCase`
- **Functions / methods**: `snake_case`
- **Constants**: `UPPER_SNAKE_CASE`
- **Private helpers**: `_leading_underscore` (e.g., `_build_bias_analysis`)
- **Pydantic models**: `PascalCase`, fields `snake_case`
- **Dataclasses**: `PascalCase`, fields `snake_case`
- **Enums**: inherit `StrEnum`; members `UPPER_SNAKE_CASE`, values `lower_snake_case`

### Logging
Use the centralized pattern from `common/io/logging.py`:
```python
import logging
logger = logging.getLogger(__name__)          # module-level

# Inside a ServiceTemplate subclass:
self.logger = getLogger(config.service_name)
```
Log at every pipeline boundary: stream in/out, model calls, DB writes.
Never use `print()` in service code. Format:
`%(asctime)s - %(levelname)s - [<container>.%(name)s] - %(message)s`

### Error Handling
- Raise domain-specific exceptions: `ProcessingError` / `RoutingError` (in `service_template.py`); `NLPError` hierarchy (`InvalidInputError`, `ModelNotReadyError`, `PipelineExecutionError`) in `microservices/nlp/errors.py`.
- Never swallow exceptions silently.
- In `ServiceTemplate` subclasses, wrap `_process_message` in `try/except` and call `self._handle_failure(message, e)` to route failed messages to the failure stream.
- In FastAPI endpoints: catch `IntegrityError` → 409, generic `Exception` → 500; always call `db.rollback()` before raising `HTTPException`.
- CUDA OOM: catch `torch.cuda.OutOfMemoryError`, call `torch.cuda.empty_cache()`, then re-raise.

### Pydantic vs Dataclasses
- **Pydantic `BaseModel`**: Redis stream payloads (`Message`, `MessageHeader`, `MessagePayload`), FastAPI DTOs.
- **`@dataclass`**: lightweight data carriers (`Article`, `SentenceScore`, `Claim`, `BiasProfile`, `ServiceConfig`).
- Use `frozen=True` on immutable dataclasses (e.g., `Article`).
- Use Pydantic v2 API: `.model_dump()` / `.model_validate()` — never `.dict()` / `.from_orm()`.

### Environment Variables
Always load via `common/env/get_env_var.py`:
```python
from common.env.get_env_var import get_env_var
MY_VAR = get_env_var("MY_VAR", str, logger, default="fallback")
```
Never call `os.getenv` directly in service logic. This provides type casting and fatal-on-missing behaviour.

---

## Architecture Constraints

- **Stream names**: `{job_type}:to.be.{stage}` for active streams; `{job_type}:failed.{stage}` for failure streams. `job_type` is `user` or `background`.
- **Shared contracts** (`common/models/`): never change stream message shapes or DB models without updating **all** producers and consumers.
- **`ServiceTemplate`** (`common/service/service_template.py`): all microservices inherit from this. Override only `_process_message(self, message: StreamMessage) -> StreamMessage`.
- **Dummy modes**: NLP and scraper services must remain functional when `DUMMY_NLP_MODE=true` — required for local dev without GPU. The `config.py` `try/except SystemExit` pattern enables component-only imports in test contexts.
- **Documentation output**: write all markdown, analysis docs, and workflow definitions to `claude_docs/<subfolder>/`. Never write docs to the project root.
- **Do not duplicate** utilities across services — use `common/redis_client/`, `common/env/`, `common/io/`, `common/model_manager/`.
- **NLP pipeline order**: Preprocessor → CentralityScorer → Embedder → EntityRecognizer → BiasDetector → CheckWorthinessFilter.
- **Data flow**: `POST /api/v1/jobs` → `user:to.be.scraped` → WebScraper → `user:to.be.nlp` → NLP → `user:to.be.retrieval` → RetrievalLayer → DB/pgvector.
