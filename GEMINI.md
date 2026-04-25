# Sentinel Backend Project Context

## Project Overview
**Sentinel** is a Misinformation Intelligence Platform designed to identify and analyze misinformation at scale. The backend is built using a **Microservices Architecture**, prioritizing scalability, asynchronous processing, and modularity.

### Core Technologies
- **Language:** Python 3.11/3.12
- **Web Framework:** FastAPI
- **Database:** PostgreSQL with `pgvector` for semantic search/embeddings.
- **Messaging/Queue:** Redis (using Streams for asynchronous communication).
- **ORM:** SQLAlchemy with `psycopg2`.
- **Infrastructure:** Docker & Docker Compose.
- **Development:** VS Code Dev Containers (strictly enforced for environment consistency).

### Architecture & Microservices
The system follows a pipeline-based processing model where messages flow through Redis streams:

1.  **API Gateway (`microservices/api/`)**: Entry point for user-submitted jobs. Publishes to `user:to.be.scraped`.
2.  **Ingestor (`microservices/ingestor/`)**: Periodically fetches RSS feeds and identifies new articles. Publishes to `background:to.be.scraped`.
3.  **Web Scraper (`microservices/web_scraper/`)**: Extracts content and metadata from URLs. Publishes to `*:to.be.nlp`.
4.  **NLP Service (`microservices/nlp/`)**: Performs Named Entity Recognition (NER), bias detection, and generates embeddings. Publishes to `*:to.be.retrieval`.
5.  **Retrieval Layer (`microservices/retrieval_layer/`)**: Performs semantic search against existing claims using `pgvector`.
6.  **Common Library (`common/`)**: Shared utilities for Redis communication, environment management, and logging used across all services.

---

## Building and Running

### Development Environment
This project **must** be developed inside the provided VS Code Dev Container.
1.  Copy `configs/.env.template` to `.env` in the root.
2.  Open in VS Code and select **"Dev Containers: Rebuild and Reopen in Container"**.

### Lifecycle Commands
All management scripts are located in the `scripts/` directory.

- **Full Reset & Deploy:**
    ```bash
    ./scripts/clean.sh && ./scripts/build.sh && ./scripts/deploy.sh
    ```
- **Deploy Specific Service:**
    ```bash
    ./scripts/deploy.sh <service_name>  # e.g., retrieval, nlp, api
    ```
- **Stop All Services:**
    ```bash
    ./scripts/down.sh
    # OR
    sudo docker-compose down
    ```
- **View Logs:**
    ```bash
    ./scripts/logs.sh <service_name>
    ```
- **Format and Lint:**
    ```bash
    ./scripts/format_and_lint.sh
    ```
- **Clear Data:**
    ```bash
    ./scripts/clear_data.sh
    ```

---

## Development Conventions

### Coding Style
- **Formatting:** Handled by `black` and `isort`.
- **Linting:** `flake8` for style and `mypy` for static type checking.
- **Type Hints:** Mandatory for all new functions and classes.
- **Asynchronous Code:** Extensive use of `asyncio` and `FastAPI`'s async endpoints.

### Shared Logic
- Do **not** duplicate logic across services. Use the `common/` package for:
    - Redis publishers/consumers (`common/redis_client/`).
    - Environment variable access (`common/env/`).
    - Logging and I/O utilities (`common/io/`).
    - Model management (`common/model_manager/`).

### Dependency Management
- **Dev Container:** Edit `.devcontainer/environment.yml` for environment-wide dependencies and rebuild.
- **Service-Specific:** Each microservice has its own `requirements.txt` for production builds.

### Communication Flow
Services communicate primarily via **Redis Streams**. When implementing a new step in the pipeline:
1.  Define the input/output stream names in `.env` (or use defaults in `docker-compose.yml`).
2.  Use the `common.redis_client` to consume from input streams and publish to output streams.
3.  Ensure message schemas are consistent between the producer and consumer.

### Testing
- Tests are located in the `tests/` directory.
- Use `pytest` for running tests.
- **Validation:** Always verify the full pipeline flow (POST to API -> Poll results) after significant changes.

### Integration Schema
- The final response format for the browser extension is documented in `expected_response.md`. This schema includes:
    - `article`: Metadata and preview.
    - `trustScore`: 0-100 overall trust metric.
    - `biasAnalysis`: Political bias and sentiment evaluation.
    - `keyClaims`: Individual claims with verdicts and evidence.
    - `relatedArticles`: Contextual reading from other sources.

---

## Key Files & Directories
- `microservices/`: Individual service source code.
- `common/`: Shared backend library.
- `scripts/`: Operational bash scripts.
- `docker/compose/docker-compose.yml`: Main orchestration file.
- `BACKEND_STATUS.md`: Current production/readiness state.
- `GEMINI.md`: This project context file.
