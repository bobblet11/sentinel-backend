# NLP Service

## What It Does

The NLP service is the analytical core of Sentinel. It transforms scraped article text into structured claims, entities, bias metadata, embeddings, and topic signals that the retrieval layer can store and search.

## Main Responsibilities

- clean and segment article text
- identify named entities
- extract the most relevant sentence candidates
- rewrite context-dependent statements into clearer standalone claims
- score claim worthiness
- generate semantic embeddings
- classify article-level bias, sentiment, and topic signals

## Key Design Points

- Built as a staged pipeline so each analytical step can enrich or filter the same working representation.
- Uses transformer-based models for several core tasks rather than relying on a single monolithic model.
- Supports GPU-aware execution for the heavier inference path.
- Uses model preloading and shared model management to reduce repeated inference overhead.
- Preserves a dummy or reduced-complexity development path so local work does not always require full production hardware.

## Pipeline Shape

At a high level, the service performs:

1. preprocessing
2. named entity recognition
3. sentence extraction
4. decontextualization
5. check-worthiness filtering
6. embedding generation
7. claim conversion
8. bias and topic enrichment

## Interfaces

- input streams: `user:to.be.nlp`, `background:to.be.nlp`
- output streams: `user:to.be.retrieval`, `background:to.be.retrieval`

## Important Files

- `main.py` for service startup
- `nlp_service.py` for the stream service wrapper
- `components/claimextract.py` for pipeline orchestration
- `components/` for stage-specific model and processing logic

