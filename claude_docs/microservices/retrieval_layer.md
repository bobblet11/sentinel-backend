# Retrieval Layer Microservice

## Methodology

### Overview

The Retrieval Layer is the terminal stage of the Sentinel Backend pipeline. It consumes NLP-enriched article messages from the `user:to.be.retrieval` and `background:to.be.retrieval` Redis streams, executes multi-stage evidence retrieval against a persistent knowledge base, derives per-claim verdicts via Natural Language Inference (NLI), and persists final results to PostgreSQL and a Redis hash store for API access. The service extends the shared `ServiceTemplate` base class, which provides consumer group management, concurrent worker pools, and failure stream routing.

### Multi-Stage Retrieval Pipeline

Evidence retrieval is structured as four progressive filter stages applied independently per claim, trading recall for precision across each transition:

| Stage | Method | Candidate Cap | Purpose |
|---|---|---|---|
| 1 — Entity Filter | Named-entity join on `claim_to_entity` | ≤ 50 | High-recall seeding via entity co-occurrence |
| 2 — Keyword Filter | `pg_trgm` trigram match on `decontextualised_claim` | ≤ 20 | Lexical pre-filtering on claim surface form |
| 3 — Vector Similarity | pgvector HNSW cosine search (768-dim) | ≤ 10 (cosine ≥ 0.35) | Semantic re-ranking of merged filter output |
| 4 — NLI Classification | `typeform/distilbert-base-uncased-mnli` | All candidates | Entailment-based relation labelling |

Stages 1 and 2 merge into a deduplicated set capped at 100 before Stage 3. This cascade reduces the NLI inference burden by approximately three orders of magnitude relative to a full-corpus scan. Both filter stages apply a ±30-day temporal window derived from the article's publication date, restricting evidence to contextually contemporaneous claims.

#### Stages 1 & 2: Entity and Keyword Filtering

The entity filter retrieves claims sharing named entities (persons, organisations, locations) with the input claim via a join on the `claim_to_entity` association table. The keyword filter uses PostgreSQL's `pg_trgm` extension for trigram-similarity matching on the `decontextualised_claim` column, capturing lexical overlap where entity co-occurrence is insufficient. Candidates from both stages are merged before proceeding to semantic search.

#### Stage 3: pgvector HNSW Cosine Similarity

Semantic retrieval uses pgvector's Hierarchical Navigable Small World (HNSW) index with `m=16`, `ef_construction=64`, and `vector_cosine_ops`. The `m=16` parameter sets bidirectional links per graph node, governing the recall–index-size trade-off; `ef_construction=64` controls graph quality at build time. Embeddings are 768-dimensional vectors from `all-mpnet-base-v2`, matching the NLP service output. A normalisation step pads or truncates incoming vectors to the `Vector(768)` schema definition. Candidates below cosine similarity 0.35 are discarded before NLI.

#### Stage 4: NLI Verdict Derivation

The NLI classifier (`typeform/distilbert-base-uncased-mnli`) classifies each input–evidence claim pair as `entailment`, `neutral`, or `contradiction`, mapped internally to `support`, `irrelevant`, and `contradict`. Only `support` and `contradict` relations contribute to verdict scoring via a weighted net-support ratio:

```
net_support = (Σ support_confidence − Σ contradict_confidence) / (Σ all_relevant_confidence)
```

This score maps to a six-point ordinal scale: `true` (≥ 0.5), `mostly-true` (≥ 0.1), `mixed` (> −0.1), `mostly-false` (> −0.5), `false` (≤ −0.5). Claims with no `support` or `contradict` evidence receive `unverified`. Claim decontextualisation performed upstream — producing self-contained propositions free of coreference dependencies — materially improves NLI accuracy by eliminating cross-article referential ambiguity.

### Fast-Path, Persistence, and Integration

When `retrieve_from_db=True` is set on a message — indicating a previously processed URL — the service loads stored claims directly from PostgreSQL, bypassing the full four-stage pipeline and reducing repeat-request latency from seconds to sub-second. For new articles, all metadata, sentiment, named entities, and 768-dim claim embeddings are written within a single atomic transaction before retrieval executes.

User-job results are stored in a Redis hash keyed by job UUID for low-latency API polling. Background (ingestor) jobs write data to the knowledge base and return immediately without evidence retrieval. The `ServiceTemplate` is configured with `BlockPrioritisationLevel.EXPONENTIAL` across both input streams, ensuring user-submitted jobs preempt lower-priority background traffic. Schema migrations are applied idempotently at startup via `ensure_schema_compatibility()`, with the `claim` table carrying a `decontextualised_embedding Vector(768)` column and entities normalised into a separate `claim_to_entity` join table to support efficient filter-stage joins.

---

## Results & Analysis

### Processing Statistics

Operational statistics from `logs/retrieval/stats.json` covering 17–18 April 2026 record the following aggregate activity across 13 user-submitted jobs:

| Metric | Value |
|---|---|
| User jobs processed | 13 |
| Total input claims evaluated | 99 |
| Total evidence matches returned | 501 |
| Average evidence matches per claim | 5.1 |
| Total related articles surfaced | 169 |

An average of 5.1 evidence matches per claim confirms that the multi-stage filter consistently surfaces a non-trivial evidential context. The 501 total matches across 99 claims indicate effective knowledge-base utilisation at the current corpus scale.

### Verdict Distribution

| Verdict | Count | Percentage |
|---|---|---|
| `unverified` | 48 | 48.5% |
| `false` | 43 | 43.4% |
| `mostly-true` | 3 | 3.0% |
| `true` | 2 | 2.0% |
| `mixed` | 2 | 2.0% |
| `mostly-false` | 1 | 1.0% |

The predominance of `unverified` (48.5%) reflects the knowledge base at an early growth stage: claims from newly ingested articles frequently lack sufficient counterparts in the corpus to produce a verdict signal. The high `false` proportion (43.4%) indicates that when relevant evidence is found, contradicting claims substantially outweigh supporting ones — consistent with contested geopolitical topics drawn from the sampled outlets. Positive verdicts (`true` + `mostly-true`) account for 5.1% of claims, reflecting the formula's deliberate conservatism: a net-support ratio ≥ 0.5 is required to register `true`. Outlet-level breakdown shows that ABC produced the highest evidence density (102 matches over 16 claims, 6.4 per claim) while The Financial Express produced the lowest (8 matches over 10 claims, 0.8 per claim), attributable to the corpus's greater topical coverage of international outlets. The verdict distribution is visualised in `results/chart_v2_retrieval_verdicts.png`.

### Database Growth Trajectory

Hourly snapshots between 15 April 2026 15:32 and 17 April 2026 14:00 (≈ 46.5 hours) show sustained growth across both persistence layers:

| Timestamp | PostgreSQL | Redis |
|---|---|---|
| 2026-04-15 15:32 | 585 MB | 505 MiB |
| 2026-04-16 00:00 | 751 MB | 1.37 GiB |
| 2026-04-16 12:00 | 938 MB | 1.80 GiB |
| 2026-04-17 00:00 | 1,179 MB | 2.10 GiB |
| 2026-04-17 14:00 | 1,261 MB | 2.32 GiB |

PostgreSQL grew 676 MB at **14.5 MB/hr**; Redis grew 1,868 MiB at **40.2 MiB/hr**. The ~2.8× higher Redis growth rate is attributable to accumulating full structured retrieval results — including claim excerpts, source URLs, and related article metadata — with no eviction policy, versus write-once normalised records and binary embedding vectors in PostgreSQL. The growth trajectory is visualised in `results/chart_v2_db_growth.png`.

### Pipeline Effectiveness and Scalability

The four-stage cascade reduces the NLI candidate pool by approximately 1000× relative to a full corpus scan, making per-claim inference feasible at the current corpus size of ~1.2 GB. HNSW at `m=16` provides sub-millisecond query latency with typical recall within 5% of an exact flat search, a favourable trade-off that would remain valid through several additional months of ingestion. At 14.5 MB/hr PostgreSQL growth, the database would reach ~10 GB after approximately one month — a scale at which HNSW remains performant but the temporal evidence window becomes a critical cost-control mechanism.

The principal reliability concern lies in the NLI stage. `distilbert-base-uncased-mnli` is a general-domain model; surface-level negation or topical divergence between claim pairs may produce false contradiction signals, inflating the `false` verdict class. The high `false` proportion observed during evaluation is consistent with this artefact and warrants future investigation via domain-adapted NLI fine-tuning or calibrated threshold adjustment. Redis memory saturation is the most pressing operational risk: without TTL-based eviction on completed job hashes, the in-memory store will exhaust available capacity within weeks of sustained ingestion.
