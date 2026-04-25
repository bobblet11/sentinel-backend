# Methodology: NLP Microservice

## Overview

The NLP microservice is the analytical core of the Sentinel fact-checking pipeline. It receives scraped article text from a Redis stream, transforms it through a sequential eight-stage processing pipeline, and emits structured output containing extracted factual claims, named entities, dense vector embeddings, and a political bias profile. These outputs are consumed by the downstream Retrieval Layer to perform semantic search against a knowledge base.

The pipeline is implemented as a single orchestrating class — `ClaimExtraction` — which instantiates and sequences all component stages. Each stage is a modular, independently testable class that operates on a shared `StreamMessage` object and a local `List[SentenceScore]` that flows from stage to stage.

---

## System Architecture Context

```
Web Scraper
    │
    │  Redis Stream: user:to.be.nlp
    ▼
NLP Microservice
    │  (8-stage pipeline per article)
    │
    │  Redis Stream: user:to.be.retrieval
    ▼
Retrieval Layer
```

The NLP service consumes from a prioritised pair of Redis streams (`user:to.be.nlp` and `background:to.be.nlp`), processing user-submitted articles ahead of background ingestor jobs. Worker concurrency and batch sizes are controlled by environment variables (`NLP_MAX_WORKERS`, `BATCH_SIZE`).

---

## Pipeline Stages

### Stage 1 — Preprocessing (`Preprocessor`)

**Model:** spaCy `en_core_web_sm` (POS tagger only; NER and lemmatizer disabled)

The raw HTML-extracted article text is noisy: it contains navigation menus, bylines, timestamps, photo credit lines, duplicate navigation items, and footer boilerplate injected by scrapers. The Preprocessor applies a four-phase cleaning strategy before the text reaches any deep learning model.

**Phase 1 — Line-level deduplication:** Lines are lowercased and compared against a `seen_lines` set. Repeated navigation labels (common in scraped HTML) are dropped on first re-occurrence.

**Phase 2 — Footer cutoff:** A compiled regex monitors for footer signals (`"More from the BBC"`, `"Related stories"`, `"Sign up for"`, `"Privacy policy"`, etc.). On the first match, processing stops entirely — all subsequent lines are discarded. This prevents the pipeline from treating boilerplate as article content.

**Phase 3 — Regex filtering:** Six pattern classes are applied in sequence:
- `time_meta_pattern` — timestamps, relative dates (`"3 hours ago"`, `"Updated Oct 12"`)
- `credits_pattern` — `"Image:"`, `"Photo:"`, `"AFP"`, `"Getty Images"`
- `ui_pattern` — `"Sign in"`, `"Subscribe"`, `"Share"`, `"Menu"`
- `byline_pattern` — `"By [Name]"`, `"writer,"`, `"correspondent"`
- `junk_pattern` — telemetry fragments, encoded paths, broken data lines
- `reuters_meta_pattern` — Reuters-specific utility blocks

Photo credit lines of the form `"Jeff Overs/BBC/Reuters."` are identified by slash structure combined with a known agency token regex; they are dropped only if spaCy finds no VERB or AUX token in the line (preserving real sentences that mention agencies inline, e.g., `"Reuters reported that..."`).

**Phase 4 — Structural repair:** Lines without terminal punctuation receive a trailing period, ensuring spaCy's sentence boundary detector splits them cleanly from the following line.

**Linguistic filtering:** After spaCy tokenises the cleaned text, any span shorter than 7 tokens that contains no VERB or AUX is dropped (e.g., section labels like `"Politics"` or `"Frank Gardner"`). Questions below the token threshold are retained.

**Output:** `List[SentenceScore]` — each entry holds the sentence text, its index, a salience score (initially 0.0), and a placeholder for the embedding vector.

---

### Stage 2 — Named Entity Recognition (`EntityRecognizer`)

**Model:** `dslim/bert-base-NER-uncased` (BERT fine-tuned on CoNLL-2003)

All preprocessed sentences are passed to a HuggingFace `pipeline("ner")` with `aggregation_strategy="simple"`, which merges sub-word tokens into whole entity spans. Inference runs in batches of 16.

Character offsets are computed cumulatively across sentences (with +1 for the implicit separator) so that entity positions are article-relative rather than sentence-relative. Entities shorter than 3 characters are discarded as noise. Duplicate entities — identified by the `(text.lower(), entity_label)` pair — are deduplicated, retaining the instance with the highest confidence score.

**Output:** `result.entities_in_article` — a deduplicated list of `Entity` objects (text, type, start_char, end_char).

NER runs over the *full* sentence list before extraction so that rare entities mentioned only once in a non-salient sentence are still captured at the article level.

---

### Stage 3 — Sentence Extraction & Deduplication (`SentenceExtraction`)

**Models:**
- Salience scoring: `bert-base-uncased` (CLS-token representation)
- Deduplication: `cross-encoder/nli-distilroberta-base` (NLI cross-encoder)

This stage reduces the full sentence list to at most `SENTENCE_EXTRACT_TOP_K` (default 15) high-value, non-redundant sentences.

**Salience scoring:** Each sentence is encoded with BERT. The CLS token vector (index 0 of `last_hidden_state`) is taken as the sentence representation. The mean of the absolute values of the CLS vector components is used as an information-density proxy. Scores are min-max normalised across the batch. This is a BertSum-style approach: the CLS token, trained on next-sentence-prediction tasks, captures how much the sentence contributes to discourse coherence.

**NLI-based deduplication:** Sentences are ranked by salience score descending. A greedy selection loop adds each candidate only if it is not entailed by any already-selected sentence. Entailment is tested using the NLI cross-encoder: for the candidate and each previously selected sentence, the probability of the `entailment` label (index 1 of the softmax) is computed. If any pair exceeds the threshold of 0.70, the candidate is considered semantically redundant and skipped. A maximum of `NLI_MAX_PAIRS = 32` NLI comparisons are made per candidate to bound quadratic growth.

**Output:** A filtered `List[SentenceScore]` sorted by original article order, with the `score` field populated.

---

### Stage 4 — Decontextualization (`Decontextualizer`) *(optional)*

**Models:**
- Question generation: `Salesforce/mixqg-base`
- Evidence retrieval: BM25Okapi (lexical)
- Question answering: `deepset/roberta-base-squad2`
- Rewriting: `google/flan-t5-base`

This stage is toggled by the `ENABLE_DECONTEXTUALIZATION` environment variable. When enabled, it rewrites each extracted sentence to be fully self-contained — resolving pronouns, ellipsis, and implicit references so that downstream retrieval does not require the surrounding article as context.

The process for each sentence follows a five-step pipeline:

1. **Unit extraction (spaCy):** Named entities, pronouns (POS=PRON), noun chunks, and root verb phrases within the sentence are identified as potentially ambiguous "units" that require external context. At most `DECONTEXT_MAX_UNITS = 6` units are processed per sentence.

2. **Question generation (mixqg-base):** For each ambiguous unit, a clarifying question is generated using the prompt `"answer: <unit> context: <sentence>"`. MixQG is fine-tuned for answer-aware question generation, producing natural-language questions.

3. **BM25 evidence retrieval:** The generated question is used as a query against all article sentences using `rank_bm25.BM25Okapi`. The top-3 sentences by BM25 score are returned as the evidence passage.

4. **QA grounding (roberta-base-squad2):** The question is answered using the BM25-retrieved evidence. Answers with confidence below 0.20 are discarded to avoid hallucinations.

5. **Declarative rewrite (flan-t5-base):** Valid Q-A pairs are converted to standalone declarative sentences via the prompt `"Convert to a declarative sentence: Q: <q> A: <answer>"`. These context sentences are concatenated and fed into a final rewrite prompt instructing the model to incorporate specific details while preserving the original's meaning.

A regex post-process strips any label prefixes (`"false:"`, `"entailment:"`, etc.) that seq2seq models occasionally prepend.

**Output:** The same `List[SentenceScore]` with sentence texts rewritten to be self-contained.

---

### Stage 5 — Check-Worthiness Filtering (`CheckWorthinessFilter`)

**Model:** `whispAI/ClaimBuster-DeBERTaV2`

**Labels:** NFS (Non-Factual Statement) | UFS (Unimportant Factual Statement) | CFS (Check-worthy Factual Statement)

This stage classifies each extracted sentence by how much it warrants fact-checking. The ClaimBuster model, fine-tuned on political debate and news corpora, produces three-class probabilities for each sentence.

Only sentences with a CFS score ≥ 0.50 are marked `is_checkworthy = True`. If the sentence count exceeds `MAX_SENTENCES_FOR_CHECKWORTHY = 40`, only the top-scoring (by salience score from Stage 3) 40 candidates are evaluated — bounding inference cost.

Inference runs in batches of 16. Sentences are evaluated independently (no cross-sentence context is used at this stage). Each `SentenceScore` object is annotated in-place with `is_checkworthy`, `claim_type`, and `confidence`.

**Graceful degradation:** If the model is unavailable (e.g., memory constraints), all sentences are marked non-check-worthy rather than crashing the pipeline.

---

### Stage 5.5 — Entity Mapping

This is a lightweight, model-free pass that links the article-level entities discovered in Stage 2 back to individual sentences. For each sentence, a case-insensitive substring scan is performed against `result.entities_in_article`. Matching entities are written to `sentence.entities`, making entity context available per-claim in downstream output.

---

### Stage 6 — Sentence Embedding (`Embedder`)

**Model:** `sentence-transformers/all-mpnet-base-v2` (768-dimensional)

All surviving sentences (regardless of check-worthiness score) are encoded into dense vectors using the MPNet-based sentence transformer. The model was selected for its strong performance on semantic textual similarity benchmarks (SBERT evaluation suite), making it well-suited for the asymmetric semantic search task performed downstream by the Retrieval Layer.

Encoding settings:
- Batch size: 32
- `normalize_embeddings=False` — raw L2-magnitude vectors are passed to pgvector for cosine similarity search
- FP16 inference on CUDA to reduce memory footprint
- `torch.inference_mode()` context to suppress gradient tracking

**Output:** `SentenceScore.embedding` populated for every sentence; the same list is returned.

---

### Stage 7 — Sentence → Claim Conversion

Sentences that are both `is_checkworthy = True` and have `confidence ≥ options.min_confidence` are committed as `Claim` objects to `result.claims_in_article`. Each Claim carries:
- The (decontextualized) sentence text
- The 768-dim embedding vector
- The list of NER entities associated with the sentence
- The check-worthiness confidence score
- Source sentence indices (for traceability)

**Fallback:** If no sentence passes the check-worthiness filter (which can happen for short or purely narrative articles), the pipeline falls back to selecting up to `options.max_claims` sentences ranked by confidence score. This ensures downstream services always receive at least one claim.

---

### Stage 8 — Bias Detection (`BiasDetector`)

**Models:**
- Political lean: `premsa/political-bias-prediction-allsides-BERT` (BERT fine-tuned on AllSides-rated articles, F1 = 0.904)
- Emotional tone: `cardiffnlp/twitter-roberta-base-sentiment-latest` (RoBERTa)

This stage runs at the article level, not the sentence level. The first 2,000 characters of the article body are classified for political lean (Left / Center / Right) and emotional tone (Negative / Neutral / Positive).

The 2,000-character limit captures the lede and early paragraphs — the portion of an article that most strongly encodes framing and editorial stance — while keeping inference time under ~1 second on CPU for most articles.

Both classifiers run independently. The political classifier uses `top_k=None` to retrieve full probability distributions across all three labels, allowing consumers to inspect the full score breakdown. The sentiment classifier is truncated to 512 tokens (transformer limit).

**Graceful degradation:** If either classifier fails, a neutral zero-confidence `BiasProfile` is stored and the pipeline continues — bias is informational metadata, not a blocking dependency.

**Output:** `result.bias_profile` with `bias_category`, `bias_analysis_confidence`, `sentiment_category`, `sentiment_analysis_confidence`.

---

## Worked Example: End-to-End Article Processing

The following traces an article through all eight stages. The example article is a realistic BBC News-style report on a tax policy announcement.

---

**Input Article (raw scraped text):**

```
Home | News | Politics | Economy | Sign in

By Sarah Mitchell BBC Political Correspondent
Updated 14 October 2024

The UK government announced on Monday that it will raise the basic rate of income 
tax by two percentage points, from 20% to 22%, starting from April 2025. Chancellor 
David Hammond said the increase was necessary to fund a £14 billion shortfall in the 
National Health Service budget.

Opposition parties condemned the move. "This is a tax on working people," said Labour 
leader James Poole. He argued the government should instead close corporate tax 
loopholes, which he estimated cost the Treasury approximately £8 billion annually.

Economic analysts at the Institute for Fiscal Studies (IFS) warned the hike could 
reduce consumer spending by up to 1.5%, potentially slowing GDP growth. The pound 
fell 0.3% against the dollar following the announcement.

Image: Jeff Overs/BBC/Reuters.
More from the BBC
Related stories
Privacy policy
```

---

### Stage 1 — Preprocessing

**Phase 2 (footer cutoff):** The line `"More from the BBC"` triggers the cutoff regex. Everything from that line onward (`"Related stories"`, `"Privacy policy"`) is discarded.

**Phase 3 (regex filtering):**
- `"Home | News | Politics | Economy | Sign in"` → dropped by `ui_pattern` (`"sign in"`, `"home"`, `"menu"`)
- `"By Sarah Mitchell BBC Political Correspondent"` → dropped by `byline_pattern` (short, matches `"by [Name]"` and `"correspondent"`)
- `"Updated 14 October 2024"` → dropped by `time_meta_pattern`
- `"Image: Jeff Overs/BBC/Reuters."` → dropped by `credits_pattern` (`"Image:"` prefix)

**Phase 4 (structural repair):** No lines require terminal punctuation repair here.

**spaCy tokenisation + linguistic filtering:** The remaining body text is tokenised into sentences. All sentences have ≥ 7 tokens and contain verbs, so none are dropped.

**Output sentences (7 total):**
```
[0] "The UK government announced on Monday that it will raise the basic rate of income tax by two percentage points, from 20% to 22%, starting from April 2025."
[1] "Chancellor David Hammond said the increase was necessary to fund a £14 billion shortfall in the National Health Service budget."
[2] "Opposition parties condemned the move."
[3] "'This is a tax on working people,' said Labour leader James Poole."
[4] "He argued the government should instead close corporate tax loopholes, which he estimated cost the Treasury approximately £8 billion annually."
[5] "Economic analysts at the Institute for Fiscal Studies (IFS) warned the hike could reduce consumer spending by up to 1.5%, potentially slowing GDP growth."
[6] "The pound fell 0.3% against the dollar following the announcement."
```

---

### Stage 2 — Named Entity Recognition

`dslim/bert-base-NER-uncased` processes all 7 sentences in a batch.

**Entities extracted (deduplicated):**

| Entity Text | Type | Confidence |
|---|---|---|
| UK government | ORG | 0.97 |
| David Hammond | PER | 0.99 |
| National Health Service | ORG | 0.98 |
| James Poole | PER | 0.96 |
| Labour | ORG | 0.95 |
| Treasury | ORG | 0.91 |
| Institute for Fiscal Studies | ORG | 0.98 |
| IFS | ORG | 0.94 |

Note: `"He"` (pronoun referencing James Poole) is not captured as a named entity — this is addressed by the Decontextualizer in Stage 4.

---

### Stage 3 — Sentence Extraction

BERT CLS-token salience scores (normalised 0–1):

| Idx | Score | Sentence (abbreviated) |
|---|---|---|
| 0 | **0.91** | "The UK government announced…" |
| 1 | **0.87** | "Chancellor David Hammond said…" |
| 5 | **0.85** | "Economic analysts at the IFS warned…" |
| 4 | **0.79** | "He argued the government should instead…" |
| 6 | **0.62** | "The pound fell 0.3%…" |
| 3 | **0.55** | "'This is a tax on working people,'…" |
| 2 | **0.31** | "Opposition parties condemned the move." |

NLI deduplication selects greedily from highest to lowest. Sentence 1 ("Chancellor David Hammond said the increase was necessary…") is checked against already-selected sentence 0 ("The UK government announced…"). The NLI cross-encoder scores their entailment probability at 0.41 — below the 0.70 threshold — so sentence 1 is retained (it adds new information about the rationale). All 7 sentences survive deduplication in this short article; `SENTENCE_EXTRACT_TOP_K = 15` is not exceeded.

---

### Stage 4 — Decontextualization

Sentence 4 (`"He argued the government should instead close corporate tax loopholes…"`) contains the pronoun `"He"` — an ambiguous unit.

1. **QG (mixqg-base):** `"answer: He context: He argued the government should instead close corporate tax loopholes…"` → Question: `"Who argued the government should close corporate tax loopholes?"`

2. **BM25 retrieval:** Query `"Who argued the government should close corporate tax loopholes?"` is matched against all sentences. Top-1 result: sentence 3 (`"...said Labour leader James Poole."`), BM25 score 4.2.

3. **QA (roberta-base-squad2):** Answer: `"James Poole"`, confidence 0.88 (≥ 0.20 threshold → accepted).

4. **Declarative rewrite (flan-t5-base):** Q-A pair → `"James Poole argued the government should close corporate tax loopholes."`

5. **Final rewrite:** `"James Poole, Labour leader, argued the government should instead close corporate tax loopholes, which he estimated cost the Treasury approximately £8 billion annually."`

The rewritten sentence is stored in `sentence.text`; the original is preserved for audit purposes.

---

### Stage 5 — Check-Worthiness Filtering

`whispAI/ClaimBuster-DeBERTaV2` classifies all 7 sentences (well under `MAX_SENTENCES_FOR_CHECKWORTHY = 40`):

| Idx | Sentence (abbreviated) | CFS Score | Result |
|---|---|---|---|
| 0 | "The UK government announced…raise income tax…" | **0.94** | ✅ Check-worthy |
| 1 | "Chancellor David Hammond said…£14 billion shortfall…" | **0.89** | ✅ Check-worthy |
| 4 | "James Poole argued…£8 billion annually." | **0.82** | ✅ Check-worthy |
| 5 | "Economic analysts…reduce consumer spending by 1.5%…" | **0.78** | ✅ Check-worthy |
| 6 | "The pound fell 0.3%…" | **0.71** | ✅ Check-worthy |
| 3 | "'This is a tax on working people,'…" | 0.38 | ❌ NFS (opinion) |
| 2 | "Opposition parties condemned the move." | 0.22 | ❌ NFS (vague) |

5 of 7 sentences are marked as factual claims worth checking.

---

### Stage 5.5 — Entity Mapping

Each check-worthy sentence is scanned for article entities by substring match. Example:

- Sentence 0 → entities: `[UK government, David Hammond]`  
- Sentence 4 → entities: `[James Poole, Labour, Treasury]`  
- Sentence 5 → entities: `[Institute for Fiscal Studies, IFS]`

---

### Stage 6 — Sentence Embedding

All 5 check-worthy sentences are encoded to 768-dim vectors using `all-mpnet-base-v2`.

Example embedding snippet for sentence 0:
```
[0.0312, -0.1847, 0.2203, 0.0891, -0.3412, ..., 0.1105]  # 768 dimensions
```

These vectors capture semantic meaning, allowing the Retrieval Layer to find related knowledge-base facts using cosine similarity via pgvector.

---

### Stage 7 — Sentence → Claim Conversion

5 `Claim` objects are committed to `result.claims_in_article`. Each carries:

```json
{
  "confidence": 0.94,
  "decontextualised_claim_text": "The UK government announced on Monday that it will raise the basic rate of income tax by two percentage points, from 20% to 22%, starting from April 2025.",
  "decontextualised_claim_embedding": [0.0312, -0.1847, ...],
  "NER_entities": [
    {"entity_text": "UK government", "type_of_entity": "ORG"},
    {"entity_text": "David Hammond", "type_of_entity": "PER"}
  ],
  "source_sentence_indices": [0]
}
```

---

### Stage 8 — Bias Detection

The first 2,000 characters of the article (which covers the full body in this case) are classified:

**Political bias (`premsa/political-bias-prediction-allsides-BERT`):**
- Left: 0.21 | **Center: 0.67** | Right: 0.12
- Result: `bias_category = "Center"`, `bias_analysis_confidence = 0.67`

**Emotional tone (`cardiffnlp/twitter-roberta-base-sentiment-latest`):**
- Negative: 0.44 | **Neutral: 0.51** | Positive: 0.05
- Result: `sentiment_category = "Neutral"`, `sentiment_analysis_confidence = 0.51`

**Final `BiasProfile`:**
```json
{
  "bias_category": "Center",
  "bias_analysis_confidence": 0.67,
  "sentiment_category": "Neutral",
  "sentiment_analysis_confidence": 0.51
}
```

---

## Final NLP Output Structure

The completed `StreamMessage` forwarded to the Retrieval Layer contains:

```
NLPResult
├── claims_in_article: List[Claim]          # 5 claims with embeddings + entities
├── entities_in_article: List[Entity]       # 8 unique named entities (article-level)
└── bias_profile: BiasProfile               # Center / Neutral, with confidence scores
```

---

## Model Summary

| Stage | Component | Model | Purpose |
|---|---|---|---|
| 1 | Preprocessor | spaCy `en_core_web_sm` | POS-guided text cleaning |
| 2 | EntityRecognizer | `dslim/bert-base-NER-uncased` | Named entity extraction |
| 3 | SentenceExtraction | `bert-base-uncased` + `cross-encoder/nli-distilroberta-base` | Salience scoring + semantic dedup |
| 4 | Decontextualizer | `Salesforce/mixqg-base` + `deepset/roberta-base-squad2` + `google/flan-t5-base` | Pronoun/reference resolution |
| 5 | CheckWorthinessFilter | `whispAI/ClaimBuster-DeBERTaV2` | Factual claim classification |
| 5.5 | Entity Mapping | *(rule-based)* | Entity–sentence linking |
| 6 | Embedder | `sentence-transformers/all-mpnet-base-v2` | 768-dim semantic vectors |
| 7 | Claim Converter | *(rule-based)* | Commit final claims |
| 8 | BiasDetector | `premsa/political-bias-prediction-allsides-BERT` + `cardiffnlp/twitter-roberta-base-sentiment-latest` | Political lean + emotional tone |

---

## Design Decisions

**Why run NER before sentence extraction?** NER runs over the full sentence list so that entities mentioned only once in a low-salience sentence (e.g., a peripheral figure quoted briefly) are still captured at the article level. If NER ran only on extracted sentences, rare entities would be lost.

**Why use CLS-token magnitude for salience?** This is a lightweight BertSum-inspired heuristic: the CLS token in BERT is trained to summarise sentence-level information for classification tasks. Its activation magnitude correlates with how information-dense the sentence is relative to the batch, without requiring a full summarisation model or reference sentences.

**Why NLI for deduplication rather than cosine similarity?** Cosine similarity between sentence embeddings detects topical relatedness but not logical entailment. Two sentences can be on the same topic but make distinct claims (e.g., "Taxes will rise 2%" vs "Taxes are rising due to a deficit"). NLI directly tests whether one sentence logically follows from another, making it more precise for removing truly redundant claims.

**Why truncate BiasDetector to 2,000 characters?** The first 2,000 characters cover the lede, sub-heading, and first several paragraphs — the content that most strongly encodes editorial framing. Truncating rather than chunking-and-aggregating keeps inference to a single forward pass, avoiding latency issues in high-throughput scenarios.

**Why unnormalised embeddings?** pgvector's `<=>` (cosine distance) operator normalises vectors internally during comparison. Storing raw vectors preserves the original magnitude information for any future components (e.g., LexRank centrality weighting) that depend on it.
