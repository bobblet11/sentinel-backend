# Web Scraper Microservice

## Methodology

### Overview

The Web Scraper microservice is responsible for the automated retrieval and extraction of article content from a predefined set of news outlets. Upon receiving a scraping job from an upstream Redis stream, the service fetches the raw HTML of the target URL, extracts structured article text and metadata, and forwards the enriched message downstream for NLP processing. The design prioritises robustness under adversarial network conditions, supporting concurrent job execution and graceful failure handling.

### Service Architecture and Stream Integration

The scraper is implemented as a subclass of the shared `ServiceTemplate` base class (`common/service/service_template.py`), which provides the Redis stream consumption loop, worker pool management, signal handling, and failure stream routing. This inheritance pattern ensures consistent lifecycle behaviour across all microservices in the pipeline.

On startup, the service registers with two input streams—`user:to.be.scraped` and `background:to.be.scraped`—corresponding to user-submitted and background ingestor jobs, respectively. Processed messages are routed to either `user:to.be.nlp` or `background:to.be.nlp` based on a `header.type` routing key, implementing a priority lane architecture. Failed messages that cannot be recovered are published to a dedicated failure stream (`user:failed.scrape` / `background:failed.scrape`) for later replay or inspection.

The service is configured via environment variables loaded through `common/env/get_env_var.py`, including `SCRAPER_MAX_WORKERS` (concurrency), `BATCH_SIZE`, `MAX_FETCH_RETRIES`, and exponential back-off parameters (`INITIAL_FETCH_DELAY_S`, `FETCH_DELAY_GROWTH_RATE`). Stream prioritisation uses `BlockPrioritisationLevel.EXPONENTIAL`, ensuring that user-submitted jobs consistently receive processing priority over background ingestion tasks under load.

### Multi-Strategy Content Extraction Pipeline

Content extraction is handled by a two-phase pipeline: an HTML fetch phase and a parse phase. Both phases are instrumented for timing and failure telemetry, and results are written to a per-container `stats.json` file for observability.

#### Phase 1 — HTML Fetching (Selenium)

Raw HTML is retrieved by the `FetchManagerSelenium` singleton (`managers/fetch_manager_selenium.py`), which drives a headless Chromium browser via `undetected-chromedriver` and `selenium-wire`. The rationale for a full browser-based approach—rather than a lightweight HTTP client—is that modern news websites increasingly rely on JavaScript-rendered content, server-side bot-detection, and dynamic paywall overlays that are opaque to traditional request libraries. Selenium enables the scraper to execute page scripts, wait for dynamic content to load, and simulate realistic browsing behaviour through configurable user-agent rotation and residential proxy routing (`managers/proxy_manager_paid.py`).

A virtual display (`pyvirtualdisplay`) is employed to run the browser headlessly within the Docker container. The fetcher implements configurable page-load timeouts (300 seconds), a scroll-based content trigger for lazy-loaded articles, and exponential retry logic for transient failures. Screenshots are captured on failure for debugging, with folder rotation to cap disk usage.

#### Phase 2 — HTML Parsing (ParseManager)

The `ParseManager` singleton (`managers/parse_manager.py`) implements a four-level cascading extraction strategy applied in order of specificity:

1. **Level 0 — RSS Metadata Strategy**: If RSS feed metadata (title, description, author, publication date) is attached to the incoming message, it is used directly. This path is fast and reliable but depends on the ingestor having populated the metadata fields.

2. **Level 1 — Hardcoded Parser Strategy**: A registry of outlet-specific `BaseParser` subclasses (`parsers/`) is consulted using URL pattern matching. Eight outlets have bespoke parsers (BBC, The Guardian, CBC, CBS, NBC, NPR, Euronews, ABC), each targeting the specific DOM structure of that outlet. This strategy produces the highest-quality extraction for known outlets, preserving article structure and metadata precisely.

3. **Level 2 — Trafilatura Strategy**: If no hardcoded parser matches or yields sufficient content (>200 characters), the library trafilatura is invoked on the raw HTML. Trafilatura is a web scraping and content extraction library designed to remove boilerplate (navigation, advertisements, comment sections) from web pages, recovering the main article body using a combination of language models and structural heuristics (Barbaresi, 2021). It also extracts author and publication date metadata where present.

4. **Level 3 — DOM Fallback Strategy**: If trafilatura fails or returns insufficient content, a generic fallback strategy strips known noisy HTML tags (`<script>`, `<style>`, `<nav>`, `<aside>`, `<footer>`, etc.) and joins all `<p>` tag contents. This is the lowest-fidelity path but ensures some text is always returned.

After a successful extraction, `_hydrate_missing_fields` enriches incomplete results by scanning OpenGraph tags, JSON-LD structured data, and standard meta tags for missing title, author, and publication date fields.

### Error Handling and Observability

Failures at either phase raise typed exceptions (`FailedToFetch`, `FailedToParse`, both subclassing `ScraperError`) which propagate to the `_process_message` handler. The exception type name is captured and written to the per-day `stats.json` under both global `errors` and per-outlet `errors` keys, enabling post-hoc analysis of failure distributions. The `ServiceTemplate` base class intercepts any uncaught exception from `_process_message` and routes the original message to the failure stream, preventing pipeline stalls.

Outlet identity is resolved via URL regex matching against a dictionary of twelve known news organisations (`OUTLET_PATTERNS`). Jobs from unrecognised URLs are attributed to an `"Unknown"` outlet bucket. Per-outlet statistics include total processing time, HTML size, extracted text size, and error counts, supporting fine-grained latency and reliability analysis.

### Dummy Mode

For local development and testing without a GPU or live browser environment, the scraper supports a dummy mode controlled by the `DUMMY_SCRAPER_MODE` environment variable. When active, the service returns synthetic article content without invoking Selenium or any network calls, allowing the full downstream pipeline (NLP, retrieval) to be exercised in isolation.

---

## Results & Analysis

### Experimental Setup

Scraper performance data was collected across three independent deployment instances over a four-day observation window (15–18 April 2026). Instance **farhan** operated on 16–18 April; instance **ben\_1** on 15–18 April; instance **ben\_2** on 15, 16, and 18 April. Each instance ran against the same set of RSS-ingested article URLs drawn from eight major English-language news outlets.

### Aggregate Throughput

Across all three instances, the scraper processed a combined total of **7,518 jobs**. Per-instance breakdowns are as follows:

| Instance | Jobs Processed | Total Time (s) | Avg Time per Job (s) | Error Rate |
|---|---|---|---|---|
| farhan | 3,183 | 221,282 | 69.5 | 53.3% |
| ben\_1 | 2,361 | 184,733 | 78.2 | 54.0% |
| ben\_2 | 1,974 | 136,448 | 69.1 | 19.2% |
| **Combined** | **7,518** | **542,463** | **72.2** | **44.5%** |

The mean scraping latency of **72.2 seconds per job** reflects the cost of headless browser instantiation, JavaScript execution, and anti-bot countermeasure navigation. The majority of this time is attributable to the Selenium fetch phase; the BeautifulSoup/trafilatura parse phase contributed negligibly (typically <2 seconds per job).

### Error Rate Analysis

Of the 7,518 jobs processed, **3,349 resulted in errors**, yielding an overall error rate of **44.5%**. Error type distribution across all instances is shown below:

| Error Type | Count | Share of Errors |
|---|---|---|
| ValueError | 2,922 | 87.2% |
| AttributeError | 285 | 8.5% |
| ReadTimeoutError | 75 | 2.2% |
| Exception (generic) | 37 | 1.1% |
| TypeError | 30 | 0.9% |

The dominant error class, `ValueError`, corresponds primarily to cases where fetched HTML was too short or empty—a signal that the target page returned an anti-bot challenge page, a soft paywall, or a redirect rather than article content. `AttributeError` errors are consistent with the hardcoded parsers encountering unexpected DOM structures, suggesting that outlet-specific templates drift over time as publishers modify their front-end markup. `ReadTimeoutError` indicates page loads that exceeded the 300-second timeout, most commonly on outlets with heavy JavaScript bundles or geographically distant servers.

*See Figure 1: `results/chart_v2_scraper_error_types.png`*

### Temporal Error Rate Trend

The combined error rate exhibited a pronounced upward trend over the four-day window:

| Date | Combined Jobs | Combined Errors | Error Rate |
|---|---|---|---|
| 15 April | 1,495 | 461 | 30.8% |
| 16 April | 3,124 | 1,011 | 32.4% |
| 17 April | 2,431 | 1,429 | 58.8% |
| 18 April | 468 | 448 | 95.7% |

The error rate escalated from approximately 31% on 15 April to 96% on 18 April. This trajectory is consistent with progressive anti-bot fingerprinting by target outlets: as the scraper's browser profile accumulated browsing history on a fixed IP/proxy configuration, outlets with sophisticated bot-detection systems (such as Cloudflare Turnstile or TLS fingerprint analysis) became increasingly likely to serve challenge pages rather than article content. The sharp deterioration on 18 April—where nearly all jobs failed—strongly suggests that one or more proxy IPs had been blocked or rate-limited by the time the observation window closed.

*See Figure 2: `results/chart_v2_scraper_error_rate.png`*

### Geographic and Instance Variance

Instance **ben\_2** recorded a markedly lower error rate of **19.2%** compared to **53.3%** (farhan) and **54.0%** (ben\_1). Since all three instances processed URLs from the same outlet set and operated over overlapping date ranges, the most plausible explanation for this divergence is geographic or ISP-level network difference. Residential proxy pools vary in IP reputation by region; if ben\_2 was routing traffic through a proxy pool with a different country allocation or cleaner IP reputation score, target servers would have been less likely to classify its requests as automated. This hypothesis is consistent with the `ReadTimeoutError` pattern, which was largely absent from ben\_2's logs, suggesting those hosts responded normally rather than hanging on challenge pages.

Notably, the per-outlet error profile of ben\_2 on ABC (75% error rate) remained high across all instances, indicating that ABC's bot-detection is particularly aggressive and geography-independent.

### Per-Outlet Latency and Volume Analysis

The eight monitored outlets were not homogeneous in either volume or latency characteristics. The table below summarises combined statistics across all instances and dates:

| Outlet | Total Jobs | Avg Latency (s/job) |
|---|---|---|
| BBC | 1,698 | 63.0 |
| The Guardian | 1,672 | 95.9 |
| ABC | 1,104 | 22.8 |
| CBS | 825 | 69.2 |
| NPR | 770 | **127.5** |
| Euronews | 517 | 39.9 |
| NBC | 486 | 88.6 |
| CBC | 414 | 69.1 |

**NPR** was the slowest outlet at an average of 127.5 seconds per job, likely due to its heavy use of client-side JavaScript rendering, which requires the browser to wait for asynchronous content hydration before the article body is accessible. **The Guardian** was second at 95.9 seconds, consistent with its multi-layer paywall and tracking-consent modal that must be navigated before content loads. **NBC** averaged 88.6 seconds, potentially attributable to its CDN configuration presenting variable load times.

At the other extreme, **ABC** reported the lowest average latency at 22.8 seconds. However, this figure must be interpreted cautiously: a per-outlet error rate of approximately 75–89% across instances (particularly farhan and ben\_1) means that a significant portion of those jobs terminated early with an empty-HTML fetch failure, artificially deflating the average time-to-completion.

*See Figure 3: `results/chart_v2_scraper_outlet_latency.png`*

### HTML-to-Text Compression Ratio

Across all instances, the scraper retrieved approximately **3.37 billion bytes** of raw HTML while extracting **23.0 million bytes** of clean article text, yielding a mean HTML-to-text compression ratio of **146.6:1**. Per-instance ratios were consistent (farhan: 145.8×, ben\_1: 153.2×, ben\_2: 142.0×), indicating that the extraction pipeline performs uniformly regardless of deployment environment. The ratio reflects the substantial proportion of a modern news page dedicated to navigation, advertising scripts, tracking pixels, and embedded media metadata—content that is correctly discarded by the trafilatura and hardcoded parser strategies.

### Summary

The Web Scraper microservice demonstrated reliable high-throughput operation under normal conditions, processing over 7,500 jobs at a mean latency of 72 seconds. The principal reliability challenge is bot-detection circumvention: the dominant failure mode (87% of errors) was empty HTML returns caused by challenge pages, and error rates compounded over time as proxy IP reputations degraded. Geographic variation between instances confirms that proxy pool quality is a significant determinant of scraping success. Future work should consider rotating proxy pools on a per-session or per-day basis, implementing adaptive back-off per outlet, and expanding the hardcoded parser registry to cover the highest-error-rate outlets (particularly ABC and NBC) with more resilient DOM selectors.

---

### References

Barbaresi, A. (2021). Trafilatura: A web scraping library and command-line tool for text discovery and extraction. *Proceedings of the 59th Annual Meeting of the Association for Computational Linguistics and the 11th International Joint Conference on Natural Language Processing: System Demonstrations*, ACL 2021, pp. 122–131.
