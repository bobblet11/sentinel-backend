# Sentinel

Sentinel is a real-time misinformation intelligence platform designed to help readers inspect news content at the moment of consumption. The backend of the Sentinel app combines claim extraction, bias analysis, semantic retrieval, and asynchronous microservice orchestration to turn raw articles into structured, evidence-backed outputs.

This repository showcases the backend system behind that workflow: a production-oriented pipeline built with FastAPI, Redis Streams, PostgreSQL, pgvector, Docker, and transformer-based NLP components.

## Problem and Motivation

Misinformation tools often solve only one part of the problem. Some systems detect whether a sentence looks check-worthy, some rate the political leaning of an outlet, and some aggregate previously published fact checks. What they usually do not provide is a unified workflow that can analyze a live article in real time, extract factual claims, surface framing bias, and retrieve related evidence across a continuously updated corpus.

Sentinel addresses that gap. The goal is not to produce a simplistic true-or-false machine, but to create a system that helps users inspect how claims are expressed, how articles are framed, and how similar claims appear across other reporting sources.

## What Sentinel Does

Sentinel supports two complementary product experiences:

- a browser extension for in-context article analysis
- a web dashboard for broader exploration of stored article intelligence

On the backend, the platform performs four core tasks:

- scrape and normalize article content from submitted URLs and monitored feeds
- extract claim-like statements and enrich them with NLP-derived metadata
- classify article-level bias and sentiment signals
- retrieve semantically related evidence from a growing news corpus

## System Architecture Overview

The backend is structured as a microservice system with two coordinated pipelines:

- a background pipeline that continuously ingests and processes articles into the knowledge base
- an on-demand pipeline that analyzes user-submitted articles in real time

The core services are:

- `api-service` for job submission and result delivery
- `ingestor-service` for RSS-based discovery of new articles
- `web_scraper-service` for URL resolution and content extraction
- `nlp-service` for analytical processing over article text
- `retrieval-layer` for evidence search, persistence, and verdict-oriented matching

Supporting infrastructure includes:

- Redis Streams for inter-service communication
- PostgreSQL for durable structured storage
- pgvector for embedding-backed similarity search
- Docker Compose for deployment and orchestration

## Pipeline Walkthrough

The backend flow is split by job type, but both paths share the same major processing stages.

### On-demand flow

```text
Client
  -> POST /api/v1/jobs
  -> user:to.be.scraped
  -> Web Scraper
  -> user:to.be.nlp
  -> NLP Service
  -> user:to.be.retrieval
  -> Retrieval Layer
  -> GET /api/v1/jobs/{uid}/result
```

### Background flow

```text
RSS feeds
  -> Ingestor
  -> background:to.be.scraped
  -> Web Scraper
  -> background:to.be.nlp
  -> NLP Service
  -> background:to.be.retrieval
  -> Retrieval Layer
  -> persistent corpus storage
```

The stream naming pattern follows `{job_type}:to.be.{stage}`, which keeps the pipeline explicit and easy to trace. Failed jobs are routed to stage-specific failure streams rather than being dropped, which preserves operational visibility and replayability.

## Technical Highlights

The backend is designed around several strong engineering ideas that make it a substantive systems project rather than a simple API wrapper.

- Two-lane priority architecture separates user work from background ingestion so interactive requests are not starved by corpus maintenance.
- Redis Streams provide persistent, decoupled stage handoff with consumer-group semantics and replayable failure handling.
- The NLP service uses transformer-based components for claim extraction, bias analysis, sentiment analysis, and semantic embedding.
- The retrieval stack combines relational filtering, vector similarity, and NLI-based reranking instead of relying on a single retrieval method.
- The system is built to run in distributed multi-instance deployments, with shared coordination over Redis and PostgreSQL.

## NLP Pipeline Deep Dive

The NLP service is the analytical core of Sentinel. It converts scraped article text into structured claims and article-level metadata that can be stored, searched, and surfaced to users.

Its major stages include:

- text preprocessing to clean and segment article content
- named entity recognition to identify people, organizations, locations, and related entities
- sentence extraction to reduce the article into high-value candidate statements
- decontextualization to rewrite context-dependent sentences into standalone claims
- check-worthiness filtering to keep only the most verification-relevant statements
- dense embedding generation for semantic retrieval
- bias and sentiment classification at the article level
- claim conversion and topic classification for downstream retrieval and presentation
- supports GPU acceleration and model preloading to keep transformer-heavy stages viable in production-style operation.

## Retrieval and Evidence Matching

The retrieval layer is responsible for turning extracted claims into evidence-backed outputs.

Instead of doing a single naive similarity search, the backend applies a retrieval cascade:

1. entity-based filtering narrows the candidate pool using claim-linked named entities
2. keyword filtering expands coverage through article-title matching
3. vector similarity search over pgvector embeddings surfaces semantically related claims
4. NLI-based classification determines whether candidate evidence supports, contradicts, or remains neutral toward the input claim

This layered approach reduces unnecessary compute early while preserving semantic depth later in the ranking process.

## Key Results and Metrics

Sentinel is beyond a conceptual prototype and operates as a deployed and evaluated platform.

To date, the system produces the following results across its deployment snapshots and evaluation runs:

- 7,954 total unique articles saved in the broader corpus snapshot
- 50,578 verifiable claims extracted across the broader deployment snapshot
- 27,354 unique named entities identified in the broader corpus snapshot
- 4,353 articles processed during the 96-hour evaluation window
- 24,252 verifiable claims extracted during that evaluation window
- 138,193 entity mentions identified during the same evaluation period
- an average of 5.6 verifiable claims extracted per article
- 99 completed user analysis jobs
- long-run ingestion deduplication efficiency above 98%

To date, the architecture demonstrates horizontal scaling across three deployment instances while preserving a shared corpus and coordinated pipeline state.

## Deployment and Scalability Story

Sentinel runs in a hybrid cloud-edge deployment model.

- Redis and PostgreSQL act as centralized coordination and persistence layers
- scraping and NLP-heavy workloads run on decentralized worker nodes
- multiple worker instances consume from shared streams using consumer-group patterns

This setup lets the system combine centralized state with distributed compute, which is a credible and technically interesting deployment strategy for transformer-heavy workloads.

## Frontend Integration Context

The backend system serves two client experiences.

- The browser extension submits article jobs and polls for completed analysis.
- The dashboard supports browsing and comparing previously processed content at larger scale.

The backend therefore is not just a data-processing pipeline; it is the service layer of a full product experience.

## Tech Stack

- Python
- FastAPI
- Redis Streams
- PostgreSQL
- pgvector
- Docker and Docker Compose
- Selenium-based scraping
- transformer-based NLP models
- React and TypeScript clients consuming backend APIs

## Service Documentation

- [API service](./microservices/api/README.md)
- [Ingestor service](./microservices/ingestor/README.md)
- [Web scraper service](./microservices/web_scraper/README.md)
- [NLP service](./microservices/nlp/README.md)
- [Retrieval layer service](./microservices/retrieval_layer/README.md)

Database setup and schema assets live under `microservices/db/`, with migration-specific notes already documented in `microservices/db/migrations/README.md`.

## Short Setup

Recommended workflow:

1. Open the repository in VS Code.
2. Reopen it inside the Dev Container.
3. Prepare a config-specific `.env` file under a directory such as `configs/base`.
4. Deploy the stack with the provided script.

Main commands:

```bash
./scripts/deploy.sh [config-name]
./scripts/clean.sh [config-name]
./scripts/clear_data.sh
./scripts/format_and_lint.sh
```

Configuration values are documented in [configs/.env.template]
