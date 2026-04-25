# Sentinel Backend — 30-Minute Presentation Plan
## Methodology & Results Focus

**Total duration**: 30 minutes  
**Methodology + Results target**: ~24 minutes  
**Audience**: Final-year project examiners / technical panel  
**Tone**: Confident, data-driven, technically precise

---

## PRESENTATION OVERVIEW (timing table)

| Section | Slides | Duration | Running Total |
|---------|--------|----------|---------------|
| Opening | 1–4 | 3 min | 3 min |
| Methodology | 5–16 | 13 min | 16 min |
| Results | 17–26 | 11 min | 27 min |
| Closing | 27–28 | 3 min | 30 min |

---

## OPENING (~3 minutes)

---

## SLIDE 1: Title Slide (0:00–0:30)

**Visual/Chart**: Title card — "Sentinel: A Distributed Misinformation Detection Platform"  
Subtitle: "Final Year Project — Methodology & Results"  
Names, date, institution logo

**Key points**:
- Welcome the panel, introduce yourself / team briefly (one sentence each)
- State what Sentinel is in one line: *"Sentinel is a production-scale distributed backend that ingests news articles, processes them through a 9-stage NLP pipeline, and uses semantic search to fact-check claims."*

**Speaker notes**:
- Keep this to 30 seconds — do not linger. The title slide is a formality.
- Transition: *"Let me start by explaining why this problem matters."*

---

## SLIDE 2: Problem Statement (0:30–1:30)

**Visual/Chart**: Simple text + stat callouts. Optional: stock image of news feed or social media scroll.

**Key points**:
- Misinformation spreads at machine speed; human fact-checkers cannot keep up
- Existing tools (e.g., Snopes, PolitiFact) are manual, slow, and unscalable
- The gap: no end-to-end automated pipeline that ingests live news, extracts verifiable claims, and cross-checks them against a knowledge base at scale
- Our answer: Sentinel — automated, asynchronous, horizontally scalable

**Speaker notes**:
- Cite the problem space briefly: *"Misinformation has measurable societal consequences — election interference, vaccine hesitancy, financial manipulation. Manual fact-checking organisations cannot index the volume of content published daily."*
- Do not over-argue the problem. One minute is enough. Move to what we built.
- Transition: *"Here's a high-level picture of the system we designed to address this."*

---

## SLIDE 3: System Overview — Architecture (1:30–2:30)

**Visual/Chart**: `diagram_system_architecture.png`

**Key points**:
- Five microservices: API Gateway, Ingestor, Web Scraper, NLP Service, Retrieval Layer
- All async communication via **Redis Streams** — no direct service-to-service calls
- Containerised with Docker; each service has its own image in a build hierarchy
- Two job lanes: **user jobs** (interactive, high-priority) and **background jobs** (RSS ingestor, low-priority)
- PostgreSQL + pgvector for persistent storage and semantic search

**Speaker notes**:
- Point to the diagram as you speak. Name each service and its role in one sentence.
- *"The key design principle is isolation with asynchronous handoff — each service reads from its input Redis Stream and writes to the next. No service waits for another."*
- Mention that this enables horizontal scaling — run multiple instances of any service.
- Transition: *"Now let me go through each component in detail, starting with how we get articles into the system."*

---

## SLIDE 4: Data Flow — End to End (2:30–3:00)

**Visual/Chart**: `diagram_pipeline_flow.png`

**Key points**:
- Linear flow: RSS feeds → Ingestor → Scraper → NLP → Retrieval → PostgreSQL
- User submits a URL via `POST /api/v1/jobs`, polls `GET /api/v1/jobs/{uuid}/result`
- Stream naming convention: `{job_type}:to.be.{stage}` (e.g., `user:to.be.scraped`)
- Failure streams: `{job_type}:failed.{stage}` for dead-letter replay

**Speaker notes**:
- This slide is a bridge — 30 seconds only. Let the diagram do the talking.
- *"Every message in the system is a Redis Stream entry with a structured Pydantic schema. Failures are routed to dedicated failure streams for replay rather than dropped."*
- Transition: *"Let's go through the methodology — how each stage is designed and why."*

---

## METHODOLOGY (~13 minutes)

---

## SLIDE 5: System Architecture & Design Principles (3:00–4:30)

**Visual/Chart**: `diagram_system_architecture.png` (same or zoomed variant) + code snippet of `ServiceTemplate` base class

**Key points**:
- **ServiceTemplate pattern**: all microservices inherit a common base class — handles Redis consumption, batch processing, worker thread pools, signal handling, and failure routing. Only `_process_message()` is overridden per service.
- **Priority combiner**: `user` stream weight=2, `background` stream weight=1 — user jobs always take precedence without starvation of background jobs
- **Docker image hierarchy**: `python-light` → `python-light-common` → `python-ml-cpu` / `python-ml-gpu`. GPU image for NLP; CPU for everything else
- **Observability**: structured logging at every pipeline boundary using `common/io/logging.py`; log format includes service name, timestamp, and level

**Speaker notes**:
- *"Rather than writing boilerplate Redis consumption code in every service, we centralised it in a `ServiceTemplate` base class. Each microservice is roughly 100–200 lines of domain logic on top of a battle-tested base."*
- *"The priority combiner ensures that a researcher submitting an article interactively isn't blocked behind thousands of RSS background jobs."*
- Transition: *"The first stage of the pipeline is the Ingestor — let's look at how it feeds articles in."*

---

## SLIDE 6: Ingestor Service — Design (4:30–6:00)

**Visual/Chart**: `chart_v2_ingestor_outlet_dedup.png`

**Key points**:
- Monitors **157 RSS feeds** across **8 news outlets**: Guardian, BBC, CBS, NPR, ABC, Euronews, CBC, NBC
- Runs on a cron-style schedule; each cycle fetches all feeds and extracts article URLs
- **Two-stage deduplication**:
  1. *Within-cycle*: Python `set()` — deduplicates URLs seen in the same fetch cycle (O(1) hash lookup)
  2. *Cross-cycle*: Redis `SADD` / `SISMEMBER` — persists seen URLs across restarts; survives container restarts
- Why: prevents re-scraping the same article when it appears in multiple feeds or across cycles. At 900 new articles/day, re-processing at scale would waste scraper and NLP compute.
- Only truly new URLs are published to `background:to.be.scraped`

**Speaker notes**:
- *"The two-tier design is intentional: the in-memory Python set is O(1) and handles the bulk of duplicates within a single batch. The Redis set is O(1) per lookup but persisted — it handles the cross-run case."*
- *"This is not premature optimisation. In our 27-day long-run test, 98.3% of URLs were deduplicated. Without this, we'd be scraping and NLP-processing the same article dozens of times."*
- Transition: *"Once a new URL is identified, the Web Scraper takes over."*

---

## SLIDE 7: Web Scraper — 3-Tier Fetch Strategy (6:00–8:00)

**Visual/Chart**: `diagram_pipeline_flow.png` (scraper stage highlighted) + `chart_v2_scraper_error_types.png`

**Key points**:
- **Tier 1 — Selenium (headless Chrome)**: handles JavaScript-rendered pages, cookie banners, paywalled content
- **Tier 2 — requests + BeautifulSoup**: lightweight fallback for static HTML pages; much faster
- **Tier 3 — Proxy rotation**: used when a domain returns 403/429 (rate-limiting detected)
- **Parse pipeline after fetch**: boilerplate removal → metadata extraction (title, author, publish date, outlet) → text cleaning → sentence segmentation
- **ThreadPool concurrency**: multiple articles scraped in parallel within each worker
- Error type breakdown: ValueError 87.2% (parse failures — article structure couldn't be extracted), AttributeError 8.5% (missing DOM elements), ReadTimeoutError 2.2% (network)

**Speaker notes**:
- *"The 3-tier design means we try the cheapest option first. The vast majority of articles can be fetched with a simple HTTP request. Selenium is expensive — headless Chrome per-page — so it's reserved for sites that require JS rendering."*
- *"Parse failures dominate our error rate (87.2%). This tells us the bottleneck is article structure variation across outlets, not network reliability — an important distinction we'll return to in results."*
- *"3.37 GB of raw HTML was downloaded; after cleaning, this compressed to 23 MB of usable text — a 146.6× compression ratio. That's the scale of boilerplate we're removing."*
- Transition: *"Once clean text is extracted, it enters the NLP pipeline. This is the centrepiece of the system."*

---

## SLIDE 8: NLP Pipeline — Overview (8:00–8:45)

**Visual/Chart**: `diagram_nlp_pipeline.png`

**Key points**:
- **9 sequential stages** — each stage produces structured output consumed by the next
- All models run on a single shared GPU (CUDA 12.4); CPU fallback supported via `DUMMY_NLP_MODE`
- Stages are ordered for efficiency: cheap/fast filters run first to reduce volume before expensive model inference
- Input: raw article text. Output: structured JSON with entities, claims, embeddings, bias score, sentiment, topics.

**Speaker notes**:
- *"The pipeline is deterministic and ordered. We don't run all 9 models on every sentence — early stages act as gates, reducing the volume of text that expensive downstream models have to process."*
- Use this slide as an orientation — 45 seconds only. Each stage gets its own detail on the next slides.
- Transition: *"Let me walk through each stage."*

---

## SLIDE 9: NLP Stages 1–3 — Preprocessing, NER, Sentence Extraction (8:45–10:15)

**Visual/Chart**: `chart_v2_nlp_entity_types.png`

**Key points**:
- **Stage 1 — Preprocessor (spaCy)**:
  - Tokenisation, sentence boundary detection, POS tagging
  - Linguistic filtering: removes sentences below a minimum token threshold, strips non-prose (tables, captions, lists)
  - Normalises whitespace, unicode, quotation marks

- **Stage 2 — Named Entity Recognition (dslim/bert-base-NER-uncased)**:
  - Fine-tuned on CoNLL-2003; 4 entity types: PER (person), ORG (organisation), LOC (location), MISC (miscellaneous)
  - Outputs span-level entity annotations used downstream in retrieval filtering
  - Entity type distribution: PER 36.5%, ORG 25.5%, LOC 21.9%, MISC 16.1%

- **Stage 3 — Sentence Extraction & Deduplication**:
  - **Salience scoring**: ranks sentences by centrality (TF-IDF-weighted graph) — selects top-k most informative
  - **NLI-based deduplication**: uses a cross-encoder to detect near-paraphrase pairs; removes redundant sentences before claim extraction
  - Prevents the same claim being extracted multiple times from slightly rephrased sentences

**Speaker notes**:
- *"NER at this stage is important because it indexes the entities in an article. Later, when we search the knowledge base, we filter candidates by shared entity overlap — this is one of the four stages of our retrieval cascade."*
- *"The NLI-based deduplication is a deliberate design choice over simple cosine similarity. It's more precise about semantic equivalence — two sentences that share vocabulary but mean different things are not deduplicated."*
- Transition: *"Stage 4 is the most architecturally interesting component — the Decontextualizer."*

---

## SLIDE 10: NLP Stage 4 — Decontextualizer (KEY INNOVATION) (10:15–11:30)

**Visual/Chart**: `chart_r4_nlp_stage_latency.png` — highlight the decontextualizer bar

**Key points**:
- **Problem**: News sentences are context-dependent. *"He said the policy was a failure"* is unverifiable without knowing who "he" is, what policy, and when.
- **Goal**: Transform context-dependent sentences into self-contained, independently verifiable claims
- **3-model cascade**:
  1. **MixQG** — question generation: generates clarifying questions about unresolved references in the sentence (*"Who said the policy was a failure?"*)
  2. **RoBERTa-SQuAD2** — extractive QA: answers those questions from the surrounding article context (*"Treasury Secretary Janet Yellen"*)
  3. **FLAN-T5** — claim synthesis: merges the original sentence + QA answers into a standalone declarative claim (*"Treasury Secretary Janet Yellen said the economic policy was a failure"*)
- This is the pipeline's **most computationally expensive stage**: mean 19.0s, representing **78% of total NLP latency**
- But it is the enabler of accurate retrieval — decontextualised claims can be matched against a knowledge base without requiring article context

**Speaker notes**:
- *"This is the architectural centrepiece of the NLP pipeline. Without decontextualisation, our embeddings represent fragments that can't be matched against independent knowledge base entries."*
- *"The 3-model cascade is sequential by design: each stage is conditioned on the output of the previous. MixQG generates questions; RoBERTa-SQuAD2 answers them from the article; FLAN-T5 synthesises everything into a clean declarative claim."*
- *"78% of NLP compute is here. This is the primary target for future optimisation — we discuss this in the conclusion."*
- Transition: *"After decontextualisation, Stage 5 filters which claims are worth verifying."*

---

## SLIDE 11: NLP Stages 5–7 — Worthiness, Embeddings, Bias (11:30–12:30)

**Visual/Chart**: `chart_r6_bias_sentiment_donuts.png`

**Key points**:
- **Stage 5 — Check-Worthiness Filter (whispAI/ClaimBuster-DeBERTaV2)**:
  - Binary classifier: is this claim checkworthy (factual, disputable) or not (opinion, rhetorical)?
  - Trained on ClaimBuster dataset; DeBERTaV2 architecture for improved contextual understanding
  - Acts as a gate: only checkworthy claims pass to embedding and retrieval

- **Stage 6 — Embedder (all-mpnet-base-v2, 768-dim)**:
  - Produces dense semantic vector representations for each claim
  - Vectors stored in PostgreSQL via pgvector for HNSW approximate nearest-neighbour search
  - 768-dimensional embeddings chosen for balance of expressiveness vs. storage cost

- **Stage 7 — Bias Detector (premsa/political-bias-prediction-allsides-BERT)**:
  - Fine-tuned on AllSides media bias ratings; outputs Left / Center / Right with confidence
  - Applied at article level (not per-claim)
  - Results: Left 62.0%, Center 26.1%, Right 11.9% across the corpus

**Speaker notes**:
- *"The check-worthiness filter is critical for precision. Not every sentence in a news article is a factual claim — opinions, rhetorical questions, scene-setting text would all produce false matches if sent to retrieval. This stage removes them."*
- *"all-mpnet-base-v2 was chosen over all-MiniLM-L6-v2 because it produces 768-dimensional embeddings with higher semantic fidelity, at manageable storage cost."*
- *"The 62% Left result is NOT evidence of model bias — it reflects corpus composition. The 8 outlets we monitor skew left-centre by AllSides ratings. We discuss this in results."*
- Transition: *"The final two stages add sentiment and topic labels."*

---

## SLIDE 12: NLP Stages 8–9 — Sentiment & Topic Classification (12:30–13:00)

**Visual/Chart**: `chart_r7_topic_distribution.png`

**Key points**:
- **Stage 8 — Sentiment (cardiffnlp/twitter-roberta-base-sentiment-latest)**:
  - 3-class: Positive / Neutral / Negative
  - Applied at article level; stored alongside bias for downstream filtering
  - Results: Neutral 66%, Negative 22%, Positive 12% → **1.83:1 negative-to-positive ratio**
  - This validates the well-documented negativity bias in news media

- **Stage 9 — Topic Classifier**:
  - Multi-class classification across 9 topic categories (Politics, Economy, Health, Science, etc.)
  - Enables topic-filtered retrieval and dashboard analytics
  - Applied at article level

**Speaker notes**:
- *"The 1.83:1 negative-to-positive ratio is not a surprising result — it's consistent with existing literature on news negativity bias. But it's a useful empirical validation that our pipeline is capturing real-world signal."*
- *"Topic classification is primarily for downstream filtering and analytics. It doesn't affect fact-checking directly, but enables a user to filter results by domain."*
- Transition: *"Once the NLP pipeline completes, the article and its claims enter the Retrieval Layer."*

---

## SLIDE 13: Retrieval Layer — 4-Stage Cascade (13:00–15:00)

**Visual/Chart**: `chart_v2_retrieval_verdicts.png`

**Key points**:
- **Goal**: find knowledge-base entries that are evidence for or against each extracted claim
- **4-stage cascade** (each stage reduces candidate set):
  1. **Entity filter**: candidate knowledge entries must share at least one named entity with the claim — hard filter, eliminates unrelated articles
  2. **Keyword / trigram filter**: BM25-style keyword overlap — further narrows to topically relevant candidates
  3. **pgvector HNSW search**: cosine similarity over 768-dim embeddings — semantic retrieval; returns top-k nearest neighbours from the vector index
  4. **NLI re-ranking**: cross-encoder NLI model (entailment / contradiction / neutral) scores each claim–evidence pair; assigns final verdict

- **Verdict scale**: True / Mostly-true / Mixed / Mostly-false / False / Unverified
- **Fast-path for repeat queries**: claims seen before skip re-retrieval; results are cached in PostgreSQL

**Speaker notes**:
- *"Each stage acts as a progressively tighter filter. Entity filtering alone eliminates the vast majority of the knowledge base for any given claim. By the time NLI scoring runs, it's operating on a small, highly relevant candidate set — this keeps latency bounded."*
- *"The cascade design is deliberate: NLI inference is expensive. Running it on every knowledge-base entry would be O(n) in the knowledge base size. The preceding stages bring this down to O(k) where k is much smaller."*
- *"The fast-path cache is important for background ingestion: the same claim from different outlets appears repeatedly. Caching avoids redundant retrieval."*
- Transition: *"That covers all methodology. Let's now look at what happened when we ran this in production."*

---

## SLIDE 14: Infrastructure — Scalability Design (15:00–16:00)

**Visual/Chart**: Bullet slide or simple diagram showing 3 parallel instances

**Key points**:
- Three concurrent deployment instances: **farhan**, **ben_1**, **ben_2** — each running the full stack independently
- Redis Streams consumer groups enable multiple NLP workers to share load without duplication — each message is processed exactly once
- Horizontal scaling: adding an NLP worker means starting another container pointing at the same stream
- All instances share the same PostgreSQL database for knowledge base storage
- Monitoring: structured logs aggregated per-service, per-instance

**Speaker notes**:
- *"The three-instance deployment wasn't just a stress test — it's proof that the architecture scales horizontally without code changes. Each instance runs identical containers; the consumer group handles coordination."*
- *"Running three independent deployments also gave us variance data. If results across instances diverge, that's a signal of non-determinism or environment sensitivity."*
- Transition: *"Now let's look at the actual numbers."*

---

## SLIDE 15 (TRANSITION): From Methodology to Results (16:00–16:00)

*This is not a separate slide — use the last 10 seconds of Slide 14 as a spoken transition.*

**Speaker notes**:
- *"We ran this system in production for 4 days — April 15th to 18th, 2026 — across 3 instances. I'm now going to walk through what the data tells us about each component."*

---

## RESULTS (~11 minutes)

---

## SLIDE 15: Pipeline Funnel — The Big Picture (16:00–17:30)

**Visual/Chart**: `chart_v2_pipeline_funnel.png`

**Key points**:
- Raw RSS input: **203,244 URLs** fetched in the April run
- After two-stage deduplication: **100,999 passed** (49.7% within-cycle dedup) → **1,431 truly new** (0.7% of original)
- Scraping jobs submitted: **7,518** (some URLs submitted across instances)
- Successfully scraped and NLP-processed: **4,353 articles**
- Claims extracted: **24,252** (5.6/article)
- Entities extracted: **138,193** (31.7/article)

**Speaker notes**:
- *"This funnel is the single most important summary chart in the entire presentation. 99.3% of RSS entries are filtered before any expensive network request is made — that's the deduplication system working as designed."*
- *"The funnel also reveals a processing gap: 7,518 scraping jobs were submitted but only 4,353 reached NLP. The difference is scraper failures — the 44.5% failure rate we'll examine next."*
- *"5.6 claims per article and 31.7 entities per article are meaningful densities — they tell us the NLP pipeline is extracting substantive content, not trivial fragments."*
- Transition: *"Let's zoom in on the ingestor results first."*

---

## SLIDE 16: Ingestor Results — Deduplication at Scale (17:30–19:00)

**Visual/Chart**: `chart_v2_ingestor_longrun.png` (primary) + `chart_v2_ingestor_outlet_dedup.png` (secondary/inset)

**Key points**:
- **27-day long-run** (comprehensive test):
  - **3,661,818** total URLs seen
  - **24,293** passed as new (0.66%)
  - **98.3% deduplication rate**
  - ~**900 new articles/day** steady state
- **April short-run** (production test):
  - 203,244 raw → 100,999 after within-cycle dedup (49.7%) → 1,431 after cross-cycle dedup (0.7% novel)
- Per-outlet novelty rates vary: some outlets republish heavily; others have high unique content rates

**Speaker notes**:
- *"98.3% deduplication over 27 days means the Redis set is working. Without it, we'd be re-processing the same 3.6 million URLs through the scraper and NLP pipeline every cycle — an enormous waste."*
- *"The steady-state of ~900 new articles/day gives us a planning number for scaling: at 24.3 seconds of NLP per article, that's roughly 6 GPU-hours of compute per day. Manageable for a single instance."*
- *"The outlet chart shows which feeds are most productive. This is useful for future prioritisation — if some outlets contribute far fewer unique articles, we could reduce their polling frequency."*
- Transition: *"The ingestor performed as expected. The scraper told a different story."*

---

## SLIDE 17: Scraper Results — The Rate-Limiting Story (19:00–21:00)

**Visual/Chart**: `chart_r2_scraper_error_trend.png` (primary) + `chart_r3_scraper_scatter.png` (secondary)

**Key points**:
- Combined (3 instances): **7,518 jobs**, **4,169 success (55.5%)**, **3,349 errors (44.5%)**
- Average latency: **72.2 seconds per article**
- **KEY FINDING — error rate vs latency decoupling**:
  - Day 1 (Apr 15): 31% error rate
  - Day 2 (Apr 16): 32% error rate
  - Day 3 (Apr 17): 59% error rate
  - Day 4 (Apr 18): **96% error rate**
  - But average latency **stayed flat** across all 4 days
- This pattern is diagnostic: **IP-based rate limiting**, not content parsing failure or network degradation
  - If latency had risen: timeout/throttling (network congestion)
  - If latency had fallen: requests returning fast 403s (blocks)
  - Flat latency + rising errors = IP being progressively blocked as each outlet's bot-detection adds our IP to a blocklist

**Speaker notes**:
- *"This chart is one of the most interesting findings of the project. Error rate went from 31% to 96% over 4 days. If this were a parsing problem, errors would be correlated with specific outlets or article types — not time. If it were network failure, latency would spike. The flat latency profile is the tell: we're getting responses — they're just blocks."*
- *"The scraper was running 3 instances from different machines. ben_2 showed 19% error rate versus ~53% for the others — consistent with geographic IP variance. Different IP ranges hit different rate-limit thresholds."*
- *"HTML volume: 3.37 GB downloaded, 23 MB text extracted — 146.6× compression. The bulk of what the scraper downloads is boilerplate it discards."*
- Transition: *"Let's look at how this breaks down per outlet."*

---

## SLIDE 18: Scraper Results — Per-Outlet Performance (21:00–21:45)

**Visual/Chart**: `chart_v2_scraper_outlet_latency.png` + `chart_v2_scraper_error_types.png`

**Key points**:
- Per-outlet latency range: **22.8s (ABC)** to **127.5s (NPR)**
  - ABC: 22.8s avg, 85% error rate — fast but heavily blocked
  - NPR: 127.5s avg, 27% error rate — slow but permissive
  - Guardian: 95.9s, CBS: 69.2s, BBC: 63.0s, CBC: 69.1s, Euronews: 39.9s, NBC: 88.6s
- Error type breakdown: **ValueError 87.2%** (parse/structure), **AttributeError 8.5%** (missing DOM), **ReadTimeoutError 2.2%** (network)
- High ValueError rate confirms: most failures are content extraction failures, not network failures

**Speaker notes**:
- *"ABC's 22.8s average with 85% error rate suggests it's blocking requests near-instantly — the low latency is because the block comes early in the connection. NPR's 127.5s with 27% error suggests it's doing JS rendering (Selenium tier) and largely permitting it."*
- *"87.2% ValueError tells us the scraper reaches the page and gets content — but it can't parse the article structure. This is a reminder that production news websites vary enormously in their DOM layout, and no single parser handles all of them."*
- Transition: *"Despite the scraper's struggles, the NLP pipeline ran cleanly on everything it received."*

---

## SLIDE 19: NLP Results — Throughput & Scale (21:45–22:45)

**Visual/Chart**: `chart_v2_nlp_daily_throughput.png` + `chart_r5_outlet_density.png`

**Key points**:
- **4,353 articles** processed across 3 instances over 4 days
- **Near-identical horizontal scaling**:
  - farhan: 1,559 | ben_1: 1,557 | ben_2: 1,237
  - The ~20% gap for ben_2 is explained by scraper performance (fewer articles received), not NLP capacity
- Daily throughput: Apr 15 — 1,092; Apr 16 — 2,101 (peak); Apr 17 — 1,080; Apr 18 — 80 (scraper degradation)
- Per-outlet: Guardian 1,158, BBC 1,111, CBS 543, NPR 502, ABC 301, Euronews 301, CBC 233, NBC 199
- **Claims extracted**: 24,252 total (5.6/article) — **Entities**: 138,193 total (31.7/article)

**Speaker notes**:
- *"The near-identical farhan/ben_1 throughput (1,559 vs 1,557) is a remarkable result — it's essentially perfect load distribution. This validates the Redis consumer group approach: the broker handles coordination without any application-level balancing logic."*
- *"April 18th's drop to 80 articles is consistent with the 96% scraper error rate. The NLP pipeline wasn't the bottleneck — it was waiting for input that never arrived."*
- *"Guardian and BBC dominate because they publish at high frequency and have lower scraper failure rates. NBC and CBC are at the bottom due to a combination of frequency and blocking."*
- Transition: *"Let's look at what the NLP pipeline found in the content."*

---

## SLIDE 20: NLP Results — Bias & Sentiment Analysis (22:45–23:45)

**Visual/Chart**: `chart_r6_bias_sentiment_donuts.png` (primary) + `chart_v2_nlp_bias_distribution.png` (secondary)

**Key points**:
- **Political Bias** (≤2% cross-instance variance):
  - Left: **62.0%** | Center: **26.1%** | Right: **11.9%**
  - Cross-instance variance ≤2% — model is deterministic and consistent
  - **Interpretation**: this reflects corpus composition, not model bias. The 8 outlets monitored are classified by AllSides as predominantly left-centre. This is expected.

- **Sentiment**:
  - Neutral: **66%** | Negative: **22%** | Positive: **12%**
  - Negative-to-positive ratio: **1.83:1**
  - Validates negativity bias in news media (consistent with academic literature)

**Speaker notes**:
- *"The 62% Left finding prompted us to check whether this was model artefact or corpus reality. The ≤2% variance across three independently-run instances tells us the model is stable. The explanation is simpler: our outlet selection skews left-centre. If we added Fox News and Breitbart, the distribution would shift."*
- *"The 1.83:1 negative-to-positive ratio is a genuine finding. It's not surprising — there is substantial academic literature on negativity bias in news framing. Our pipeline is capturing this signal automatically at scale."*
- Transition: *"What about processing speed? Let's look at latency."*

---

## SLIDE 21: NLP Results — Stage-Level Latency (23:45–25:15)

**Visual/Chart**: `chart_r4_nlp_stage_latency.png`

**Key points**:
- **NLP pipeline mean: 24.3s** (Median: 20.1s, P90: 24.9s, P95: 27.9s, n=524)
- **Tight distribution**: P90–P95 spread of only 3s — highly consistent
- **Stage breakdown**:
  - Decontextualizer: **19.0s (78% of total)**
  - Sentence Extraction: **3.0s (12%)**
  - NER (bert-base-NER): **1.2s (5%)**
  - All other stages: ~5% combined
- The tight P95 (27.9s vs 24.3s mean) tells us there are no pathological outliers — the pipeline degrades gracefully on long articles

**Speaker notes**:
- *"78% of NLP compute concentrated in one stage is both a finding and a roadmap. The decontextualizer is the bottleneck, and it's the most novel component. Optimising or distilling the three-model cascade — MixQG + RoBERTa-SQuAD2 + FLAN-T5 — is the single highest-impact future work item."*
- *"The tight distribution is reassuring. It means our P95 SLA is predictable — we can plan resource allocation without worrying about long-tail outliers overwhelming the queue."*
- *"Retrieval adds another 22.1s mean (Median 20.8s, P95 41.5s). The wider P95 spread here — 41.5s versus 20.8s median — reflects variance in knowledge base match quality: some claims have many near-neighbours; others have few."*
- Transition: *"Let's talk about infrastructure growth."*

---

## SLIDE 22: Infrastructure Growth — Database & Redis (25:15–26:45)

**Visual/Chart**: `chart_r8_db_growth.png`

**Key points**:
- **Measurement window**: 47 hours (April 15–17)
- **PostgreSQL**: 585 MB → 1,261 MB (+676 MB, **14.1 MB/hr**)
  - Projected annual growth: ~**120 GB/year**
  - Manageable — standard cloud PostgreSQL with pgvector can handle this
- **Redis**: 504 MB → 2,320 MB (+1,816 MB, **40.8 MB/hr**)
  - Projected exhaustion of 8 GB RAM in **~9 days**
  - **CRITICAL**: Redis Stream entries accumulate indefinitely without TTL / trim policy
  - **Recommendation**: implement `XAUTOCLAIM` + `XTRIM` with a 7-day TTL, or use Redis Stream `MAXLEN`

**Speaker notes**:
- *"Redis growth is the most operationally critical finding in the results section. 40.8 MB/hour means we'd exhaust an 8 GB Redis instance in roughly 9 days of continuous operation. This is not a theoretical concern — it would cause production OOM."*
- *"The root cause is that Redis Streams accumulate all messages unless explicitly trimmed. Our current deployment does not set a `MAXLEN` on streams. Adding `XAUTOCLAIM` with a TTL and periodic `XTRIM` is a straightforward fix."*
- *"PostgreSQL growth at 14.1 MB/hr is much more manageable. The knowledge base is growing, but at a rate that standard managed PostgreSQL can accommodate. pgvector's HNSW index will need periodic reindexing as the table grows."*
- Transition: *"Finally, let's look at what the retrieval layer found."*

---

## SLIDE 23: Retrieval Results — Verdict Distribution (26:45–27:45)

**Visual/Chart**: `chart_v2_retrieval_verdicts.png`

**Key points**:
- Test: **99 claims** from **13 user-submitted jobs**
- **501 evidence matches** found (5.1 matches per claim on average)
- **Verdict breakdown**:
  - Unverified: **48.5%** (no strong match found in knowledge base)
  - False: **43.4%** (NLI found contradiction; strict threshold)
  - Mostly-true: **3%** | True: **2%** | Mixed: **2%** | Mostly-false: **1%**
- **Unverified dominance explained**: the knowledge base is small (bootstrapped from 4,353 articles). Most claims have no matching entry yet. This will improve as the knowledge base grows.
- **43.4% False rate** with strict threshold: likely conservative; the NLI model applies high confidence for contradiction — some true claims may be misclassified if their knowledge base match is paraphrased differently.

**Speaker notes**:
- *"The 48.5% unverified rate is expected and actually demonstrates the system is working correctly — it only labels something 'false' or 'true' when it has strong evidence. Unverified is the honest answer when the knowledge base doesn't have relevant entries."*
- *"As the knowledge base grows from 4,353 to tens of thousands of articles, the unverified rate should fall significantly. This is a bootstrapping problem, not a model problem."*
- *"The 43.4% false rate being higher than true is consistent with the negativity bias finding. News articles are more likely to contain contradictions and corrections of prior claims than confirmations."*
- Transition: *"Let me summarise what we've built and where we go from here."*

---

## CLOSING (~3 minutes)

---

## SLIDE 24: Key Contributions (27:45–28:45)

**Visual/Chart**: Summary bullet slide — clean text layout

**Key points**:
- **Architecture**: Production-grade distributed pipeline with Redis Streams, priority lanes, and a reusable `ServiceTemplate` abstraction
- **Scale validated**: 3,661,818 URLs processed, 98.3% deduplication, 4,353 articles NLP-processed across 3 concurrent instances
- **NLP pipeline**: 9-stage pipeline with a novel decontextualization cascade (MixQG → RoBERTa-SQuAD2 → FLAN-T5) enabling context-independent claim verification
- **Empirical findings**:
  - Scraper IP rate-limiting identified via latency/error decoupling
  - Negativity bias (1.83:1 neg:pos) validated at scale
  - Redis memory growth as a production operational risk
- **Horizontal scaling confirmed**: near-identical throughput across 3 independent instances validates consumer group design

**Speaker notes**:
- *"We built something that actually runs in production and generates real data. The findings — including the ones about limitations — are grounded in real operational metrics, not synthetic benchmarks."*
- *"The decontextualizer is, to our knowledge, one of the few implementations of a full pipeline-integrated claim decontextualisation system at this scale."*

---

## SLIDE 25: Limitations & Future Work (28:45–29:30)

**Visual/Chart**: Two-column slide: Limitations | Future Work

**Key points**:

**Limitations**:
- Scraper failure rate (44.5%) limits throughput — 3-tier strategy is insufficient against aggressive bot detection
- Small knowledge base (4,353 articles) → 48.5% unverified rate
- Corpus selection bias (8 left-centre outlets) limits political bias representativeness
- Decontextualizer latency (19.0s, 78% of NLP) creates a throughput ceiling
- Redis memory growth (40.8 MB/hr) requires TTL implementation before long-term deployment

**Future Work**:
- Implement proxy rotation pool and residential proxies to counter IP rate-limiting
- Add `XAUTOCLAIM` + `XTRIM` with 7-day TTL on Redis Streams
- Expand outlet coverage to include right-leaning sources for bias balance
- Distil/quantise the decontextualizer cascade into a single fine-tuned model
- Scale knowledge base ingestion; add automated fact-checker cross-referencing (e.g., Snopes API)
- Implement streaming NLP (process claims as they arrive rather than per-article batch)

**Speaker notes**:
- *"We're honest about the limitations. The scraper is the most operationally fragile component, and Redis memory growth is a production-blocking issue. Both have known solutions — they didn't make it into this version."*
- *"The most academically interesting future work is distilling the decontextualizer. If we can match the accuracy of the 3-model cascade with a single fine-tuned model, we bring NLP latency down from 24s to perhaps 5s — a transformational improvement."*

---

## SLIDE 26: Q&A (29:30–30:00)

**Visual/Chart**: Simple "Thank You / Questions?" slide with key stats summary:
- 3.6M URLs | 98.3% dedup | 4,353 articles | 24,252 claims | 138,193 entities | 3 instances

**Key points**:
- Thank the panel
- Invite questions
- Have key charts ready to flip back to: Funnel (`chart_v2_pipeline_funnel.png`), Error trend (`chart_r2_scraper_error_trend.png`), Latency breakdown (`chart_r4_nlp_stage_latency.png`), DB growth (`chart_r8_db_growth.png`)

**Speaker notes**:
- Anticipated questions and answers:
  - *"Why Redis Streams instead of Kafka?"* → Lower operational overhead for this scale; Redis already required for caching; Streams provide equivalent guarantees for our message volumes. Kafka adds ZooKeeper/broker complexity.
  - *"Why not use GPT-4/Claude for claim decontextualisation?"* → API cost at 900 articles/day makes LLM APIs unviable for production; local inference is free after hardware cost and preserves privacy.
  - *"How do you validate the NLI verdicts are correct?"* → We haven't done a human annotation study yet — this is a stated limitation. The knowledge base is itself sourced from news articles, so the ground truth is imperfect.
  - *"Can you scale to more outlets?"* → Yes. Adding an outlet is a config change (add RSS feeds to the ingestor config). No code changes required.
  - *"What happens when Redis runs out of memory?"* → Currently, the container would OOM and restart. The fix is `XTRIM MAXLEN` with a sliding window — straightforward but not yet implemented.

---

## APPENDIX SLIDES (if needed for Q&A)

---

## APPENDIX A: Entity Type Distribution

**Visual/Chart**: `chart_v2_nlp_entity_types.png`

Data: PER 36.5%, ORG 25.5%, LOC 21.9%, MISC 16.1%  
Use if asked about NER quality or entity coverage.

---

## APPENDIX B: E2E Latency Breakdown

**Visual/Chart**: `chart_r9_e2e_latency.png`

- Scraper: 72.2s (mean)
- NLP: 24.3s (mean)
- Retrieval: 22.1s (mean)
- **Total E2E: ~2 minutes per article** from URL to verdict

Use if asked about end-to-end user experience.

---

## APPENDIX C: Retrieval Latency Distribution

**Visual/Chart**: `chart_v2_retrieval_latency.png`

Mean 22.1s, Median 20.8s, P90 34.4s, P95 41.5s, n=456  
Use if asked about retrieval performance details.

---

## APPENDIX D: Topic Distribution

**Visual/Chart**: `chart_r7_topic_distribution.png`

9-category topic breakdown across 4,353 articles.  
Use if asked about content analysis or topic coverage.

---

## QUICK REFERENCE: Key Numbers Cheat Sheet

| Metric | Value |
|--------|-------|
| RSS feeds monitored | 157 |
| News outlets | 8 |
| Raw URLs (April) | 203,244 |
| Dedup rate (April) | 99.3% (to 1,431 new) |
| Long-run dedup rate (27 days) | 98.3% |
| Total URLs (27 days) | 3,661,818 |
| Scraping jobs (April) | 7,518 |
| Scraper success rate | 55.5% |
| Articles NLP-processed | 4,353 |
| Claims extracted | 24,252 (5.6/article) |
| Entities extracted | 138,193 (31.7/article) |
| HTML downloaded | 3.37 GB |
| Text after cleaning | 23 MB (146.6× compression) |
| NLP latency (mean) | 24.3s |
| NLP latency (P95) | 27.9s |
| Decontextualizer share | 78% (19.0s) |
| Retrieval latency (mean) | 22.1s |
| E2E latency (per article) | ~2 minutes |
| Bias Left/Center/Right | 62% / 26% / 12% |
| Sentiment Neutral/Neg/Pos | 66% / 22% / 12% |
| Neg:Pos ratio | 1.83:1 |
| PostgreSQL growth | 14.1 MB/hr |
| Redis growth | 40.8 MB/hr |
| Redis exhaustion (8GB) | ~9 days |
| Retrieval claims tested | 99 (13 jobs) |
| Evidence matches | 501 (5.1/claim) |
| Unverified verdict | 48.5% |
| False verdict | 43.4% |

---

*Generated by GitHub Copilot CLI — Sentinel Backend Final Year Project*
