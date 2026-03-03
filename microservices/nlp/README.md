# NLP Microservice

Consumes scraped articles from a Redis stream, runs them through an 8-stage NLP
pipeline to extract verifiable claims, and publishes enriched results downstream.

---

## Table of Contents

1. [Overview](#overview)
2. [Pipeline Architecture](#pipeline-architecture)
3. [Components](#components)
4. [Models](#models)
5. [Configuration](#configuration)
6. [Pipeline Constants](#pipeline-constants)
7. [Running Locally (Test Pipeline)](#running-locally-test-pipeline)
8. [Running as a Service](#running-as-a-service)
9. [Docker](#docker)
10. [Dummy Mode](#dummy-mode)
11. [Directory Structure](#directory-structure)

---

## Overview

The NLP service receives `StreamMessage` objects from Redis, builds an `Article`
model, and passes it through `ClaimExtraction` — a single orchestrating component
that runs all pipeline stages in sequence. The final `NLPResult` (claims, entities,
bias profile) is written back onto the message and published to the output stream.

```
Redis input stream
      │
      ▼
 NLPService._process_message()
      │
      ▼
 ClaimExtraction.run(article, result, options)
      │  (8 internal stages)
      ▼
 NLPResult → Redis output stream
```

---

## Pipeline Architecture

```
┌───────────────────────────────────────────────────────────────────────────┐
│ Stage 1  Preprocessor          Raw text → List[SentenceScore]             │
│ Stage 2  EntityRecognizer      Sentences → result.entities_in_article     │
│ Stage 3  SentenceExtraction    BertSum salience + NLI deduplication       │
│ Stage 4  Decontextualizer      QG → QA → QA2D → rewrite (self-contained)  │
│ Stage 5  CheckWorthiness       Rule-based confidence scoring              │
│ Stage 5.5 Entity Mapping       Links article entities onto sentences       │
│ Stage 6  Embedder              768-dim MPNet sentence embeddings           │
│ Stage 7  Sentence → Claim      Filter + commit to result.claims_in_article│
│ Stage 8  BiasDetector          Political bias + emotional tone (optional)  │
└───────────────────────────────────────────────────────────────────────────┘
```

All intermediate state flows through a local `List[SentenceScore]` object.
No component writes directly to `result` until Stage 7, so partial failures
never corrupt the output.

---

## Components

### Stage 1 — `Preprocessor` (`components/preprocess.py`)

Cleans raw HTML/article text and tokenizes it into `SentenceScore` objects using
spaCy (`en_core_web_sm`). Applies two layers of filtering:

- **Line-level**: drops photo credit lines (`/`-separated attribution strings
  shorter than `PHOTO_CREDIT_MAX_LEN` chars with no verb, e.g. `"Jeff Overs/BBC/Reuters."`)
- **Sentence-level**: drops spans with fewer than `PREPROCESS_MIN_TOKENS` tokens
  that contain no verb/auxiliary (unless they are questions)

Returns `List[SentenceScore]`.

### Stage 2 — `EntityRecognizer` (`components/ner.py`)

Runs `NER_MODEL` (`dslim/bert-base-NER-uncased`) over the article text to extract
named entities. Deduplicates by `(text.lower(), label)` and writes to
`result.entities_in_article`. Does **not** modify the local sentence list.

### Stage 3 — `SentenceExtraction` (`components/sentenceextract.py`)

Scores sentences using BertSum-style CLS embeddings (`BERT_SCORING_MODEL`), then
runs NLI cross-encoding (`NLI_MODEL`) to drop near-duplicate sentences above
`NLI_ENTAILMENT_THRESHOLD`. Returns a top-k (`SENTENCE_EXTRACT_TOP_K`) filtered
`List[SentenceScore]`.

### Stage 4 — `Decontextualizer` (`components/decontext.py`)

Makes each extracted sentence self-contained using a four-step sub-pipeline:

1. **Question Generation** (`QG_MODEL`)
   — generates questions whose answers would provide missing context
2. **Question Answering** (`QA_MODEL`)
   — answers those questions using the full article body (BM25 evidence
   retrieval; top `BM25_TOP_K` sentences per query); answers below
   `QA_SCORE_THRESHOLD` are discarded
3. **QA → Declarative** (`GEN_MODEL`)
   — converts Q-A pairs to declarative statements; discards any output that
   ends with `?` (failed conversion guard)
4. **Final Rewrite** (`GEN_MODEL`)
   — combines original sentence + declarative context into one fluent,
   self-contained claim; rejects rewrites longer than `DECONTEXT_REWRITE_RATIO`×
   the original

### Stage 5 — `CheckWorthiness` (`components/checkworthy.py`)

Rule-based spaCy scorer. Assigns confidence in `[0, 1]` based on:

| Signal | Weight |
|---|---|
| ≥1 named entity | +0.30 |
| ≥2 named entities | +0.10 |
| Numeric quantity present | +0.40 |
| Reporting verb (said, claimed…) | +0.10 |
| Action verb | +0.10 |
| Speculative language (might, could…) | −0.50 |

Threshold: `CW_THRESHOLD` (default `0.60`). Sets `SentenceScore.is_checkworthy`.

### Stage 5.5 — Entity Mapping

Links article-level entities from `result.entities_in_article` onto each
`SentenceScore.entities` list by case-insensitive substring match. This enables
per-claim entity metadata without re-running NER per sentence.

### Stage 6 — `Embedder` (`components/embedder.py`)

Produces 768-dimensional sentence embeddings using `EMBEDDING_MODEL`. Runs in
fp16 on CUDA. Uses `datasets.Dataset` for batched encoding (`EMBEDDER_BATCH_SIZE`).
Stores vectors in `SentenceScore.embedding`.

### Stage 7 — Sentence → Claim

Promotes `SentenceScore` objects to `Claim` objects (written to
`result.claims_in_article`). Only sentences that pass **both** conditions are
promoted:

```python
s.is_checkworthy and s.confidence >= options.min_confidence  # fallback: CLAIM_MIN_CONFIDENCE
```

`Claim` stores `confidence`, `source_sentence_indices`, `decontextualised_claim_text`,
`decontextualised_claim_embedding`, and `NER_entities`. Raw original text is
**not** duplicated; the API layer hydrates it from the article body via index.

### Stage 8 — `BiasDetector` (`components/bias.py`) *(optional)*

Analyses the full article body for:

- **Political bias** — zero-shot NLI with `BIAS_POLITICAL_MODEL` over Left / Center
  / Right hypotheses; article truncated to `BIAS_MAX_CHARS` characters
- **Emotional tone** — sentiment with `BIAS_SENTIMENT_MODEL`

Writes to `result.bias_profile`. Runs only when `options.enable_bias_detection`
is `True`. Failures are caught and logged but do **not** abort the pipeline —
claims are already committed at this point.

---

## Models

| Component | Model | Task |
|---|---|---|
| EntityRecognizer | `dslim/bert-base-NER-uncased` | Token classification |
| SentenceExtraction | `bert-base-uncased` | CLS salience scoring |
| SentenceExtraction | `cross-encoder/nli-distilroberta-base` | NLI deduplication |
| Decontextualizer | `mrm8488/t5-base-finetuned-question-generation-ap` | Question generation |
| Decontextualizer | `deepset/roberta-base-squad2` | Extractive QA |
| Decontextualizer | `google/flan-t5-base` | QA2D + final rewrite |
| Embedder | `sentence-transformers/all-mpnet-base-v2` | Sentence embeddings |
| BiasDetector | `typeform/distilbert-base-uncased-mnli` | Political bias (NLI) |
| BiasDetector | `cardiffnlp/twitter-roberta-base-sentiment-latest` | Emotional tone |

All models are downloaded automatically from HuggingFace Hub on first run.

---

## Configuration

### Environment Variables

Loaded from `.env` or the container environment. Only required when running as a
service (`main.py`) — components can be imported and tested without them.

| Variable | Type | Description |
|---|---|---|
| `INPUT_STREAMS` | `str` | Comma-separated Redis stream names to consume from |
| `USER_OUTPUT_STREAM` | `str` | Redis stream for user-priority results |
| `BACKGROUND_OUTPUT_STREAM` | `str` | Redis stream for background-priority results |
| `FAILURE_OUTPUT_STREAM` | `str` | Redis stream for failed messages |
| `GROUP_NAME` | `str` | Redis consumer group name |
| `CONSUMER_NAME` | `str` | Redis consumer instance name |
| `NLP_MAX_WORKERS` | `int` | Thread pool size (set to 1; pipeline is not thread-safe) |
| `BATCH_SIZE` | `int` | Number of messages to pull per Redis read cycle |
| `DUMMY_NLP_MODE` | `bool` | `true` skips all model loading; returns canned results |
| `USE_GPU` | `bool` | `true` enables CUDA for all model pipelines |
| `NLP_NER_MODEL` | `str` | Override `NER_MODEL` (default: `dslim/bert-base-NER-uncased`) |
| `NLP_EMBEDDING_MODEL` | `str` | Override `EMBEDDING_MODEL` (default: `sentence-transformers/all-mpnet-base-v2`) |
| `NLP_BIAS_MODEL` | `str` | Override `BIAS_POLITICAL_MODEL` (default: `typeform/distilbert-base-uncased-mnli`) |

### NLPOptions (runtime)

| Field | Default | Description |
|---|---|---|
| `min_confidence` | `0.75` | Minimum check-worthiness score for claim promotion |
| `max_claims` | `10` | Maximum claims returned per article |
| `enable_bias_detection` | `True` | Whether to run Stage 8 |

---

## Pipeline Constants

All pipeline-tuning constants live in `config.py` (top of file, above the service
environment block). Edit them there without touching any component code.

### Thresholds

| Constant | Default | Effect |
|---|---|---|
| `CLAIM_MIN_CONFIDENCE` | `0.60` | Stage 7 fallback when `NLPOptions.min_confidence` is not set |
| `CW_THRESHOLD` | `0.60` | Minimum score for `SentenceScore.is_checkworthy = True` |
| `NLI_ENTAILMENT_THRESHOLD` | `0.70` | NLI probability above which a sentence is dropped as redundant |
| `QA_SCORE_THRESHOLD` | `0.35` | QA answers below this confidence are discarded in decontextualisation |

### Model Names

| Constant | Default model |
|---|---|
| `NER_MODEL` | `dslim/bert-base-NER-uncased` |
| `EMBEDDING_MODEL` | `sentence-transformers/all-mpnet-base-v2` |
| `BERT_SCORING_MODEL` | `bert-base-uncased` |
| `NLI_MODEL` | `cross-encoder/nli-distilroberta-base` |
| `QG_MODEL` | `mrm8488/t5-base-finetuned-question-generation-ap` |
| `QA_MODEL` | `deepset/roberta-base-squad2` |
| `GEN_MODEL` | `google/flan-t5-base` |
| `BIAS_POLITICAL_MODEL` | `typeform/distilbert-base-uncased-mnli` |
| `BIAS_SENTIMENT_MODEL` | `cardiffnlp/twitter-roberta-base-sentiment-latest` |

### Batch & Sequence Limits

| Constant | Default | Used in |
|---|---|---|
| `NER_BATCH_SIZE` | `16` | `EntityRecognizer` |
| `CW_BATCH_SIZE` | `32` | `CheckWorthiness` spaCy pipe |
| `EMBEDDER_BATCH_SIZE` | `32` | `Embedder` |
| `SENTENCE_SCORING_BATCH` | `16` | `SentenceExtraction` CLS pass |
| `NLI_MAX_PAIRS` | `32` | `SentenceExtraction` dedup cap |
| `DECONTEXT_GEN_BATCH_SIZE` | `8` | `Decontextualizer` QG / QA2D |
| `BM25_TOP_K` | `3` | Evidence sentences per BM25 query |
| `BERT_MAX_LENGTH` | `512` | Tokenizer truncation (BERT/NLI/QG) |
| `DECONTEXT_MAX_GEN_LENGTH` | `128` | Max output tokens for rewrites |
| `DECONTEXT_MAX_UNITS` | `6` | Ambiguous units resolved per sentence |
| `DECONTEXT_REWRITE_RATIO` | `2.5` | Reject rewrites longer than N× original |
| `BIAS_MAX_CHARS` | `2000` | Article characters fed to bias classifier |
| `BIAS_SENTIMENT_MAX_LEN` | `128` | Sentiment pipeline token truncation |

### Preprocessing Filters

| Constant | Default | Effect |
|---|---|---|
| `PREPROCESS_MIN_TOKENS` | `7` | Sentences shorter than this (without a verb) are dropped |
| `PHOTO_CREDIT_MAX_LEN` | `120` | Lines shorter than this with a slash + agency token are dropped |
| `SENTENCE_EXTRACT_TOP_K` | `10` | Max sentences kept after Stage 3 extraction |

---

## Running Locally (Test Pipeline)

The test runner at `tests/test_pipeline.py` exercises the pipeline against a JSON
article file without requiring Redis.

**Article JSON format:**
```json
{
  "article_title": "...",
  "article_text": "...",
  "article_url": "https://...",
  "article_summary": "..."
}
```

**Run the orchestrator (end-to-end via `ClaimExtraction`):**
```bash
cd microservices/nlp
python tests/test_pipeline.py article5.json --mode orchestrator
```

**Run staged mode (each component individually with per-stage timing):**
```bash
python tests/test_pipeline.py article5.json --mode staged
```

**Run both:**
```bash
python tests/test_pipeline.py article5.json --mode both
```

Output is saved to `tests/test_output_<article_name>.json`.

> **Note:** Run from `microservices/nlp/` with the `nlp311` conda environment
> active and the workspace root (`sentinel-backend/`) on `PYTHONPATH` (the test
> script adds this automatically).

---

## Running as a Service

```bash
cd /mnt/e/finalyear/sentinel-backend
python -m microservices.nlp.main
```

The service will:
1. Connect to Redis using the configured streams
2. Load all pipeline models into memory (takes ~30–60s on first run)
3. Begin consuming messages in a loop, processing one at a time (`is_concurrent=False`)
4. Gracefully shut down on `SIGINT` / `SIGTERM`

---

## Docker

Build and run via the project-level `docker-compose.yml`:

```bash
docker compose -f docker/compose/docker-compose.yml up nlp
```

The Dockerfile (`microservices/nlp/Dockerfile`):
- Extends `sentinel/base-image:1.0`
- Installs Python dependencies from `requirements.txt`
- Downloads `en_core_web_sm` spaCy model
- Verifies CUDA availability at build time
- Entrypoint: `python -m microservices.nlp.main`

---

## Dummy Mode

Set `DUMMY_NLP_MODE=true` to skip all model loading and return a canned
`NLPResult` with a single dummy claim. Useful for integration testing of
upstream/downstream services without GPU requirements.

```bash
DUMMY_NLP_MODE=true python -m microservices.nlp.main
```

---

## Directory Structure

```
microservices/nlp/
├── main.py                   # Entrypoint: configures and starts NLPService
├── nlp_service.py            # NLPService: Redis consumer + pipeline dispatcher
├── config.py                 # Pipeline constants + environment variable loading
├── requirements.txt          # Python dependencies
├── Dockerfile
│
├── components/               # One file per pipeline stage
│   ├── preprocess.py         # Stage 1 — text cleaning + tokenization
│   ├── ner.py                # Stage 2 — named entity recognition
│   ├── sentenceextract.py    # Stage 3 — salience scoring + NLI deduplication
│   ├── decontext.py          # Stage 4 — self-contained claim rewriting
│   ├── checkworthy.py        # Stage 5 — rule-based check-worthiness
│   ├── embedder.py           # Stage 6 — sentence embeddings
│   ├── bias.py               # Stage 8 — political bias + emotional tone
│   └── claimextract.py       # Orchestrator — wires Stages 1–8
│
├── models/
│   └── base.py               # Abstract NLPComponent base class
│
└── tests/
    ├── test_pipeline.py      # Local integration test runner
    ├── article.json          # Sample article (default)
    ├── article3.json         # Additional test articles
    ├── article5.json
    └── test_output_*.json    # Generated output files
```
