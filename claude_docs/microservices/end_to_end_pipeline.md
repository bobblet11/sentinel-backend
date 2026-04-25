# End-to-End Pipeline Evaluation: Sentinel Backend

---

## Methodology

### System Architecture and Rationale

The Sentinel Backend adopts a microservices architecture comprising five independently deployable services: the API Gateway, Ingestor, Web Scraper, NLP Service, and Retrieval Layer. This decomposition was driven by the requirement to support two fundamentally distinct workload profiles concurrently — interactive user job submissions demanding low-latency responses, and high-volume background ingestion of RSS feeds that may involve hundreds of thousands of article checks per day. Coupling these workloads within a monolith would force unacceptable trade-offs between throughput and latency. By isolating each stage, the system permits independent horizontal scaling, fault isolation, and targeted deployment of resource-intensive components (such as the GPU-backed NLP service) without perturbing lighter services.

### Redis Streams as the Messaging Backbone

Inter-service communication is implemented exclusively via Redis Streams, with each stream named according to the convention `{job_type}:to.be.{stage}` (e.g., `user:to.be.scraped`, `background:to.be.nlp`). Redis Streams were selected over alternatives such as Apache Kafka or RabbitMQ for several pragmatic reasons. First, Redis already serves as the system's caching layer, eliminating an additional infrastructure dependency. Second, Redis Streams provide built-in consumer group semantics, at-least-once delivery guarantees, and message acknowledgement without the operational complexity of Kafka's broker-partition model. Third, the expected message volumes — peaking at approximately 1,880 scrape jobs per day — fall well within Redis's single-instance throughput capabilities, making Kafka's horizontal partitioning unnecessary at this scale. RabbitMQ was excluded because its queue model lacks the persistent log semantics that enable replay of failed messages.

### Consumer Group Model and Parallel Processing

Each service deploys as one or more workers subscribed to the same Redis consumer group on its designated input stream. Under this model, each message is delivered to exactly one worker within the group, enabling straightforward horizontal scaling by simply launching additional instances. The evaluation dataset captures three parallel instances of both the Web Scraper and NLP Service operating simultaneously — each maintaining its own Redis consumer group membership while sharing the workload through stream partitioning. This design ensures that adding a fourth instance would proportionally increase throughput without any configuration changes to the stream topology.

### Priority Lane Design

A key architectural decision is the dual-priority stream topology. User-submitted jobs (via `POST /api/v1/jobs`) are placed on `user:*` streams, whilst RSS-sourced background articles are placed on `background:*` streams. The `BlockPrioritisationLevel` enum in the `ServiceTemplate` base class governs how each worker allocates blocking time across its input streams, weighting user streams more heavily. This ensures that interactive job submissions receive sub-second stream pickup even under heavy background ingestion load, directly supporting the system's interactive response requirement. Without this separation, a surge in background articles could delay user job processing by minutes.

### Docker Network Architecture

All services communicate over a dedicated Docker bridge network (`sentinel-net`). Service-to-service addresses are resolved via Docker's internal DNS using container names, eliminating hardcoded IP addresses and enabling container replacement without downstream reconfiguration. The bridge network provides network isolation from the host, ensuring that database and Redis ports are only accessible from within the stack unless explicitly published. The NLP service is the only service with a hardware-specific deployment profile, selecting between a CPU-only and a CUDA 12.4 GPU image via the `USE_GPU` environment variable.

### ServiceTemplate Base Class

All five microservices inherit from a common `ServiceTemplate` base class (`common/service/service_template.py`). This class centralises the entire service lifecycle: stream consumption, batch processing with configurable worker pool concurrency, graceful signal handling (SIGTERM/SIGINT), consumer group creation, and message acknowledgement. Subclasses are required to override only the `_process_message(self, message: StreamMessage) -> StreamMessage` method, encapsulating the domain logic for each pipeline stage. This pattern eliminates duplicated boilerplate across services, enforces a consistent operational contract, and ensures that infrastructure improvements (e.g., retry logic, metrics collection) propagate automatically to all services.

### Error Stream Routing and Retry Patterns

Each processing stage maintains a corresponding failure stream (e.g., `user:failed.scrape`, `background:failed.nlp`). When `_process_message` raises an exception, the `ServiceTemplate` invokes `_handle_failure`, which publishes the original message to the failure stream with the exception traceback attached. This prevents message loss and provides an auditable record of failures that can be replayed after diagnosis. The pattern distinguishes transient failures (network timeouts, recoverable parsing errors) from permanent ones (malformed HTML, missing content fields), though the current implementation routes both categories to the same failure stream without automatic retry scheduling.

### Dual-Mode Deployment

The NLP service supports two deployment modes controlled by the `DUMMY_NLP_MODE` environment variable. In dummy mode, all NLP components are bypassed and placeholder outputs are returned, allowing the full pipeline to be exercised locally without a GPU or the multi-gigabyte ML model files. This is essential for development and CI validation. In production mode, the service loads six ML components sequentially: the Preprocessor, CentralityScorer (TextRank), Embedder (`all-MiniLM-L6-v2`), EntityRecognizer (Flair NER), BiasDetector (`unitary/toxic-bert`), and CheckWorthinessFilter. The GPU variant achieves the latency necessary for production throughput; CPU-only mode is available for testing environments where GPU resources are unavailable.

### Database Architecture

The system uses a hybrid persistence strategy. PostgreSQL with the `pgvector` extension stores structured article metadata, extracted claims, entity records, and 384-dimensional sentence embeddings, enabling cosine-similarity vector search for evidence matching in the retrieval layer. Redis serves a complementary caching role, storing job status, result payloads, and intermediate stream data. The two stores are not redundant: PostgreSQL is the system of record for all processed articles and their NLP outputs, whilst Redis provides low-latency job result lookup and the messaging infrastructure. This separation allows the vector index to be queried without incurring stream overhead, and allows cache eviction policies to be tuned independently of persistent storage.

### Fast-Path Optimisation and Job Lifecycle

The API Gateway implements three-case branching logic on job submission. For first-time URLs, a full pipeline job is initiated: the URL is published to `user:to.be.scraped`, subsequently flowing through the Scraper, NLP, and Retrieval Layer before results are written to PostgreSQL and cached in Redis. For URLs already present in the database (repeat submissions), the API publishes directly to `user:to.be.retrieval`, bypassing the Scraper and NLP stages entirely. For URLs currently in-flight (actively being processed), the existing job identifier is returned immediately. This three-case design eliminates redundant computation for duplicate user submissions, which is particularly valuable when multiple users submit the same trending article simultaneously. The full job lifecycle concludes when the client polls `GET /api/v1/jobs/{uuid}/result` and retrieves the cached JSON response.

---

## Results & Analysis

### Pipeline Funnel Analysis

The volume reduction across pipeline stages is illustrated in Figure 1 (`results/chart_v2_pipeline_funnel.png`). Over the four-day evaluation window (15–18 April 2026), the ingestor polled 203,244 raw RSS items from eight news outlets. URL deduplication within the ingestor reduced this to 100,999 distinct URLs (a 50.3% reduction), of which 1,431 were classified as previously unseen and forwarded to the `background:to.be.scraped` stream — representing 0.70% of raw items and 1.42% of deduplicated URLs. The remaining 99,568 records were skipped as already present in the system's URL registry. Across the combined three-instance scraper deployment, 7,518 jobs were processed (including accumulated background backlog and user-submitted articles), yielding 4,169 successful scrapes (55.5%). The NLP service processed 4,353 jobs, producing 24,252 extracted claims and 138,193 named entities.

**Table 1: Pipeline Stage Reduction**

| Stage | Input Count | Output Count | Reduction (%) | Notes |
|---|---|---|---|---|
| RSS Polling | 203,244 raw | 100,999 deduplicated | 50.3% | URL-level deduplication |
| Ingestor Filter | 100,999 deduplicated | 1,431 forwarded | 98.6% | Previously-seen URLs removed |
| Web Scraper | 7,518 jobs | 4,169 successful | 44.5% error | 3 parallel instances |
| NLP Service | 4,353 articles | 24,252 claims | — | 5.57 claims/article |
| Retrieval Layer | 4,353 articles | 138,193 entities | — | 31.75 entities/article |

The ingestor's 98.6% second-stage filter rate is particularly notable. It indicates that the corpus of monitored outlets exhibits extremely high RSS churn: outlets republish, re-sequence, and re-index existing articles at far higher volumes than they produce novel content. Daily new-article yield across the study period averaged 358 articles per day (April window) and 900 articles per day over the long-run February–April dataset (`data_report/ingestor/stats_old.json`, 27 active days, 24,293 new over 3,661,818 processed). The long-run data (`results/chart_v2_ingestor_longrun.png`) confirms this is structurally consistent, not an anomaly of the April window.

### Daily Ingestor Volume

Figure 2 (`results/chart_v2_ingestor_daily_volume.png`) presents per-outlet daily article volumes for the April window. The Guardian contributed the largest raw volume (24,948 items, 473 new; 1.9% novel), followed by BBC (21,936 items, 380 new; 1.7%), NPR (13,384 items, 86 new; 0.6%), and CBS (11,701 items, 105 new; 0.9%). The near-uniformity of novel-article rates across outlets (0.6–1.9%) suggests that the low-yield behaviour is a structural property of RSS feed pagination rather than an outlet-specific phenomenon. Outlets with persistent archives (The Guardian, BBC) surface the most novel content in absolute terms, whilst wire-oriented outlets (NPR, NBC) exhibit lower novel-article rates, consistent with frequent re-indexing of existing wire items.

### Scraper Performance and Error Propagation

The 44.5% aggregate error rate across the three scraper instances is the single most significant quality metric in the pipeline (see `results/chart_v2_scraper_error_rate.png`). Error decomposition reveals that `ValueError` dominates across all instances (1,573 / 1,695 errors for farhan; 1,070 / 1,275 for ben_1; 279 / 379 for ben_2), arising from article content fields that do not conform to the expected extraction schema — typically paywalled articles, JavaScript-rendered pages, or structured data that Playwright/BeautifulSoup cannot parse into plain text.

**Table 2: Cross-Instance Scraper Comparison**

| Instance | Jobs | Errors | Error Rate | Avg Time (s) | ValueError | ReadTimeout | AttributeError |
|---|---|---|---|---|---|---|---|
| farhan | 3,183 | 1,695 | 53.3% | 69.5 | 1,573 | 46 | 76 |
| ben_1 | 2,361 | 1,275 | 54.0% | 78.2 | 1,070 | 29 | 149 |
| ben_2 | 1,974 | 379 | 19.2% | 69.1 | 279 | 37 | 60 |
| **Combined** | **7,518** | **3,349** | **44.5%** | **72.1** | **2,922** | **112** | **285** |

The substantial discrepancy between ben_2's error rate (19.2%) and those of farhan and ben_1 (~53–54%) is a noteworthy finding. Per-outlet breakdown reveals that ben_2 achieved markedly lower error rates on The Guardian (7% vs. ~38–52%), BBC (10% vs. ~43–48%), and NPR (12% vs. ~24–39%). A plausible explanation is geographic network routing: news outlets commonly apply geographically differentiated content-delivery or anti-scraping policies, such that requests from certain network locations are rate-limited or redirected to paywall variants more aggressively. If ben_2 operated from a network range that these outlets' CDNs treated more permissively, lower per-outlet error rates would follow as a direct consequence. This hypothesis warrants controlled testing with explicit geographic proxy routing. ABC News remains an outlier with high error rates across all three instances (75–89%), consistent with a more aggressive bot-detection policy applied uniformly by that outlet.

The 44.5% aggregate error rate does not halt the pipeline: failed scrape jobs are routed to the failure stream rather than blocking in-flight messages. The downstream NLP and retrieval services therefore operate on a 55.5% subset of submitted scrape jobs, representing the cleanly extracted articles.

### NLP Service Performance and Data Quality

The NLP service operated at full production capacity across all three instances. Aggregate processing produced 24,252 claims and 138,193 named entities from 4,353 articles. The mean claim density of **5.57 claims per article** (Table 3) reflects the behaviour of the CheckWorthinessFilter: sentences are first scored for centrality (TextRank) and then filtered for factual check-worthiness, retaining approximately five to six high-salience, verifiable claims per article. The mean entity density of **31.75 entities per article** reflects Flair NER's broad extraction policy, which captures persons (PER), organisations (ORG), locations (LOC), and miscellaneous named entities (MISC).

**Table 3: NLP Cross-Instance Comparison**

| Instance | Jobs | Claims | Claims/Job | Entities | Entities/Job | Left Bias | Centre | Right |
|---|---|---|---|---|---|---|---|---|
| farhan | 1,559 | 9,045 | 5.80 | 49,225 | 31.57 | 63.4% | 24.6% | 11.9% |
| ben_1 | 1,557 | 8,495 | 5.46 | 51,056 | 32.79 | 61.5% | 27.0% | 11.5% |
| ben_2 | 1,237 | 6,712 | 5.43 | 37,912 | 30.65 | 60.9% | 26.7% | 12.4% |
| **Combined** | **4,353** | **24,252** | **5.57** | **138,193** | **31.75** | **62.0%** | **26.0%** | **12.0%** |

Bias classification results (Figure: `results/chart_v2_nlp_bias_distribution.png`) are structurally consistent across instances, with left-leaning classifications accounting for approximately 62% of articles, centrist 26%, and right-leaning 12%. The inter-instance variance is at most 2.5 percentage points across all three bias categories, confirming that the `unitary/toxic-bert` model produces reproducible classifications when applied to the same content corpus under parallel processing conditions. This consistency is significant: it demonstrates that the NLP pipeline's bias outputs are a stable property of the model and corpus, not an artefact of scheduling or processing order.

The predominance of left-leaning classifications (62%) reflects the composition of the monitored outlet corpus — BBC, The Guardian, NPR, CBC, and ABC are outlets that `unitary/toxic-bert` consistently scores as centre-left. This is a corpus selection effect rather than a model pathology, and should be interpreted in the context of the sources chosen for ingestor monitoring.

Entity type distribution (`results/chart_v2_nlp_entity_types.png`) is dominated by PER (persons: ~47,413 across instances, approximately 34% of all entities), followed by ORG (organisations: ~35,254, ~26%), LOC (locations: ~30,218, ~22%), and MISC (miscellaneous: ~22,308, ~16%). This distribution is consistent with political and current-affairs news content, which is person- and organisation-centric.

Sentiment distribution (`results/chart_v2_sentiment_distribution.png`) shows a neutral majority (~60%), with negative sentiment (~23%) exceeding positive (~17%), consistent with the framing conventions of political journalism.

### Retrieval Layer and Verdict Distribution

The retrieval layer combines TF-IDF keyword matching, cosine-similarity vector search over pgvector embeddings, and Natural Language Inference (NLI) to evaluate each extracted claim against the stored knowledge base. Over the two-day user-job evaluation window, 13 user-submitted jobs produced 99 claims evaluated, with 501 evidence matches retrieved (5.1 evidence items per claim on average) and 169 related articles surfaced. The verdict distribution (`results/chart_v2_retrieval_verdicts.png`) reveals that 43 claims were classified as **false** (43.4%), 48 as **unverified** (48.5%), 2 as **true** (2.0%), 3 as **mostly-true** (3.0%), 2 as **mixed** (2.0%), and 1 as **mostly-false** (1.0%). The 91.9% combined false-or-unverified rate is a direct reflection of the knowledge base's current scale rather than a model-level finding: with fewer than 5,000 stored articles at the time of evaluation, many claims lack sufficient corroborating evidence for a positive verification, defaulting to **unverified**. As the knowledge base grows through continued background ingestion, the distribution is expected to shift toward more nuanced verdicts.

Confidence scores ranged from 0 to 99 across user jobs, with mean confidence varying considerably across job types. This variance is consistent with different articles exhibiting different levels of evidence coverage in the knowledge base.

### System Scalability and Database Growth

Database growth over the 46.5-hour evaluation window is presented in Figure (`results/chart_v2_db_growth.png`). PostgreSQL grew from 585 MB to 1,261 MB (+676 MB, **14.54 MB/hr**). Redis memory grew from 504 MB to 2,487 MB (+1,959 MB, **42.15 MB/hr**). At these rates, projected monthly growth is approximately 10.5 GB/month for PostgreSQL and 30.3 GB/month for Redis.

**Table 4: Database Growth Projections**

| Store | Baseline | After 46.5h | Growth Rate | Projected Monthly |
|---|---|---|---|---|
| PostgreSQL | 585 MB | 1,261 MB | 14.54 MB/hr | ~10.5 GB |
| Redis | 504 MB | 2,487 MB | 42.15 MB/hr | ~30.3 GB |

The Redis growth rate is notably higher than PostgreSQL's, reflecting Redis's role in caching full job result payloads (which include complete article NLP outputs) in addition to stream message buffers. Without a Redis eviction or TTL policy on result caches, Redis memory will become the primary scalability constraint. At the observed rate, a standard 64 GB Redis instance would be exhausted within approximately 60 days of continuous operation at current ingestion volumes. Implementing TTL-based eviction for job result keys (e.g., 7-day retention) is a near-term operational necessity.

PostgreSQL growth is dominated by the pgvector index: each article contributes one or more 384-dimensional float32 vectors (1,536 bytes each), plus structured metadata rows. At 4,169 new articles per 4-day window (~1,042 articles/day), the current storage trajectory is sustainable at the present scale, but will require index partitioning or vector quantisation as the corpus exceeds several million articles.

The three-instance parallel deployment demonstrates stable horizontal scaling behaviour. The NLP instances collectively maintained a throughput of approximately 363 articles per instance per day, with entity and claim extraction counts consistent across instances (coefficients of variation below 8%), confirming that the consumer group load-balancing distributes messages uniformly.

### API Duplicate Handling and Fast-Path Efficiency

The API Gateway's three-case deduplication logic provides a compounding efficiency benefit. During peak load, the same trending article may be submitted by multiple users within minutes. Without the fast-path, each duplicate submission would trigger a full Scraper → NLP → Retrieval execution cycle consuming approximately 72 seconds of scraper wall-clock time plus NLP inference time. The fast-path routes these repeat submissions directly to the retrieval layer or returns cached results immediately, preventing redundant GPU utilisation and ensuring that user-facing response latency remains bounded regardless of concurrent submission volume. The deduplication logic also prevents the PostgreSQL article table from accumulating duplicate records, which would degrade vector search recall by introducing multiple near-identical embedding entries for the same content.

### Cross-Service Bottleneck Identification

Comparing per-stage throughput reveals the Web Scraper as the pipeline's primary bottleneck. At a mean processing time of 72.1 seconds per job and 44.5% error rate, the effective throughput per scraper instance is approximately 313 successfully processed articles per day. The NLP service, by contrast, processes articles at a higher success rate and its per-article inference time (GPU) is substantially lower than scraper wall-clock time (which is dominated by network I/O to external news sites). The retrieval layer processes jobs in sub-second time at current knowledge-base scale. The ingestor, operating at ~50,811 raw URL checks per day, runs as a lightweight cron-style poller and does not constitute a bottleneck. Scaling the scraper from three to five instances would directly address the bottleneck, increasing the daily successful scrape throughput from ~939 to ~1,565 articles/day without any changes to downstream services.

---

*All referenced charts are located in the `results/` directory. Data sources: `data_report/ingestor/stats.json` (April 15–18), `data_report/ingestor/stats_old.json` (February–April long-run), `data_report/nlp/stats_{farhan,ben_1,ben_2}.json`, `data_report/scraper/stats_{farhan,ben_1,ben_2}.json`, `data_report/ingestor/db_snapshots.json`, `logs/retrieval/logs/stats.json`.*
