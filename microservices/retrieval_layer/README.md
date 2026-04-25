# Retrieval Layer Service

## What It Does

The retrieval layer is the final analytical stage of the backend. It persists structured outputs from the NLP pipeline, finds related evidence from the stored corpus, and assembles the claim-level matches that power user-facing results.

## Main Responsibilities

- store processed article intelligence in PostgreSQL
- use embeddings and metadata to find related claims
- narrow candidate evidence through multiple retrieval stages
- assign support or contradiction-oriented signals to retrieved evidence
- make completed results available to the rest of the system

## Key Design Points

- Uses a retrieval cascade instead of a single search strategy.
- Combines entity filtering, keyword filtering, vector similarity, and NLI-style validation.
- Relies on pgvector so semantic retrieval stays close to the main relational store.
- Treats persistence and retrieval as part of one backend responsibility rather than splitting them into separate services.
- Includes duplicate-prevention and retry-oriented logic to keep stream processing stable.

## Retrieval Shape

The service typically narrows evidence in stages:

1. entity-aware filtering
2. keyword-based narrowing
3. embedding similarity search
4. NLI-style evidence classification

## Interfaces

- input streams: `user:to.be.retrieval`, `background:to.be.retrieval`
- output: persisted database records and completed result material for API-facing retrieval

## Important Files

- `main.py` for service startup
- `services/retrieval_service.py` for stream consumption and orchestration
- `retrieval/pipeline.py` for retrieval sequencing
- `retrieval/` for the layered matching components
