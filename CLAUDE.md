# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Prompt Safeguards (apply these before doing anything else)

Before acting on any prompt, run through these checks in order:

1. **Use an agent first** — Check whether a specialized agent fits the task. If yes, delegate to it. Only work inline if no relevant agent exists or the task is trivially small. See the full agent table below.

2. **Record every change** — After ANY agent or inline action that modifies files, invoke `change-journal` to record a structured entry. This is mandatory, not optional.

3. **Preserve end-to-end stability** — Every change must leave the full pipeline (scrape → NLP → retrieval → API) in a working state. Do not break the happy path. If a change risks destabilizing E2E, flag it and propose a safe approach before proceeding.

4. **Respect component boundaries** — Services communicate via Redis Streams and well-defined Pydantic schemas. Changes to one service must not silently break another. When touching interfaces (stream message shapes, API DTOs, DB models), check all consumers before changing.

5. **Prioritize observability** — When adding or changing logic, ensure failures are visible. Prefer explicit logging at pipeline boundaries (stream in/out, model calls, DB writes) over silent failures. Use the existing `common/io/logging.py` patterns.

6. **NLP changes need extra care** — The NLP pipeline is the most frequently changed area. When modifying any component (Embedder, BiasDetector, EntityRecognizer, etc.), verify the component contract (inputs/outputs) is unchanged or update all dependents. Dummy mode must remain functional for local dev.

7. **Balanced quality** — Apply pragmatic trade-offs. Write clean, tested code where it matters (interfaces, shared logic, NLP pipeline). Move faster on isolated, low-risk changes. Do not over-engineer.

8. **Output goes to `claude_docs/`** — All markdown, context docs, and workflow definitions must be written to `claude_docs/` in an appropriate subfolder. Never write docs to the project root.

---

## Agent Usage

**Rule: always invoke the most specific matching agent before doing any work inline.** Scan the prompt against the routing table below — if ANY row matches, delegate immediately without asking. Only work inline if no agent fits AND the task is trivially small (single-file read-only lookup or a one-line fix). Always invoke `change-journal` after any file modification, inline or via agent.

### Prompt → Agent Routing

Read the user's prompt and match it to the first applicable row:

| If the prompt involves… | Use this agent |
|---|---|
| Adding a feature, refactoring a service, changing an interface, touching more than one file with architectural implications | `systems-planner` first, then `plan-executor` |
| "implement the plan", "execute the plan", "apply the changes in claude_docs" | `plan-executor` |
| "evaluate", "compare", "what's the best way to", "is there a better", "options for", "should we use X or Y", "improve the [NLP component]" | `research-and-plan` |
| "run the pipeline", "test the pipeline", "check for regressions", "is anything broken", "stress test", "debug the pipeline" | `pipeline-debugger` |
| "commit", "push", "create a PR", "merge", "revert", "branch", "resolve conflicts", "git" | `github-repo-manager` |
| "how does X work", "explain", "what is", "where is", "which service", "what env vars", "how is X configured", "what does X do" | `repo-oracle` |
| "make sure everything is in sync", "sync agents", "starting a new sprint", "agents are out of date", "just merged", "update context" | `sentinel-orchestrator` |
| "find files", "search for", "where is this defined", "which files contain", "explore" | `Explore` |
| Any multi-step research, cross-service investigation, or open-ended question requiring many file reads | `general-purpose` |
| Files were modified (by any agent or inline) | `change-journal` — always, after every change |

### Full Agent Reference

| Agent | Responsibility |
|---|---|
| `systems-planner` | Codebase audit, dependency mapping, risk assessment, plan generation before any significant change |
| `plan-executor` | Safely implements a plan from `claude_docs/` with dependency checking and rollback |
| `research-and-plan` | Researches alternatives, evaluates trade-offs, hands off brief to `systems-planner` |
| `pipeline-debugger` | E2E pipeline stress-testing and regression detection across all stages |
| `github-repo-manager` | All git operations: commits, branches, merges, reverts, PRs |
| `change-journal` | Records structured journal entry after every file modification |
| `sentinel-orchestrator` | Re-syncs context docs and agent instructions with current codebase state |
| `repo-oracle` | Read-only authoritative answers about repo architecture, config, and structure |
| `Explore` | Fast codebase searches: files, keywords, structural questions |
| `Plan` | Implementation strategy design and architectural trade-off evaluation |
| `general-purpose` | Open-ended multi-step research or complex cross-codebase investigations |
| `claude-code-guide` | Questions about Claude Code CLI, Anthropic API, or Agent SDK |

## Project Overview

Sentinel Backend is a microservices-based fact-checking pipeline. Articles are scraped, processed through an NLP pipeline, and matched against a knowledge base using semantic search to detect bias and verify claims.

**Current priority**: Stabilize and fully validate the end-to-end pipeline so it can be debugged reliably, and ensure component interfaces are clean enough that NLP models and pipeline stages can be swapped with minimal friction. Consumers include internal developers, end users via a UI, and automated ingestor pipelines.

## Commands

### Deployment
```bash
./scripts/deploy.sh [CONFIG_NAME]    # Build and deploy all services
./scripts/clean.sh [CONFIG_NAME]     # Stop and remove services
./scripts/clear_data.sh              # Wipe database and Redis data
```
Config names: `base`, `nlptest`, `benchmark-1`. Copy `configs/.env.template` to `configs/.env` before first deploy.

### Linting & Formatting
```bash
./scripts/format_and_lint.sh         # autoflake → isort → black → flake8 → mypy
```
- `black` line length: 88
- `flake8` ignores: E501, E203, W503
- mypy config: `mypy.ini`

### Tests
```bash
pytest tests/                        # Run all tests
pytest tests/sprint4/                # Run sprint-specific tests
```
Tests are sprint-organized under `tests/sprint0/` through `tests/sprint4/`, plus `tests/benchmarks/`.

### Running Services Locally
```bash
python -m microservices.api.app.main
python -m microservices.nlp.main
python -m microservices.web_scraper.main
python -m microservices.ingestor.main
python -m microservices.retrieval_layer.main
```

## Architecture

### Data Flow
```
Client POST /api/v1/jobs
  → API Service (port 8001)
  → Redis Stream: user:to.be.scraped
  → Web Scraper
  → Redis Stream: user:to.be.nlp
  → NLP Service
  → Redis Stream: user:to.be.retrieval
  → Retrieval Layer (semantic search + DB store)
  → Client GET /api/v1/jobs/{uuid}/result
```

Background jobs (from RSS ingestor) use parallel `background:*` streams with lower priority than `user:*` streams.

### Service Communication
- **Redis Streams** — all async inter-service messaging; consumer groups for load balancing
- **PostgreSQL + pgvector** — persistent storage and semantic vector search
- **Docker bridge network** (`sentinel-net`) — service-to-service connectivity

### Key Patterns

**ServiceTemplate base class** (`common/service/service_template.py`): All microservices inherit from this. It handles Redis stream consumption, batch processing, worker pools, signal handling, and failure stream routing.

**Prioritized streams**: User jobs use `user:*` streams; background (ingestor) jobs use `background:*` streams. The `BlockPrioritisationLevel` enum controls priority weighting.

**Failure streams**: Messages that fail processing are published to failure streams (e.g., `user:failed.scrape`) for replay.

**Dummy modes**: NLP and scraper services support a dummy mode for local development without GPU/browser dependencies. Set via environment variables.

### NLP Pipeline Components (in order)
1. **Preprocessor** — text cleaning
2. **CentralityScorer** — sentence importance ranking
3. **Embedder** — `all-MiniLM-L6-v2` sentence embeddings
4. **EntityRecognizer** — Flair NER
5. **BiasDetector** — `unitary/toxic-bert` political bias
6. **CheckWorthinessFilter** — claim relevance filtering

### Common Library (`common/`)
- `models/api/` — Pydantic request/response DTOs
- `models/database/` — SQLAlchemy ORM models
- `redis_client/` — stream producer/consumer utilities
- `model_manager/` — ML model loading and lifecycle
- `service/service_template.py` — service base class
- `env/` — environment variable loading
- `io/logging.py` — centralized logging

### Docker Images (build hierarchy)
```
python-light:3.11/3.12           # minimal Python
  → python-light-common:3.11/3.12  # + common lib deps
    → python-ml-cpu:3.12           # + ML libraries (CPU)
    → python-ml-gpu:3.12-cuda124   # + ML libraries (GPU/CUDA 12.4)
```

### Environment Variables
Key variables from `configs/.env.template`:
- `COMPOSE_PROFILES` — which services to start (comma-separated: api, ingestor, scraper, nlp, retrieval)
- `USE_GPU` — toggle GPU/CPU image for NLP service
- `*_STREAM_IN` / `*_STREAM_OUT` — per-service Redis stream names
- PostgreSQL and Redis connection parameters
- NLP model names (embedding, NER, bias detection models)

### Output
Store all markdown files, context documents, and workflow definitions in the folder `claude_docs/`, grouping them by subfolder according to the agent that generated them or the workflow they describe. This applies to any project documentation, analysis outputs, or process definitions created during a session — do not write these files to the project root or other locations.