# Section 4: Results and Analysis — Writing Plan

> **Purpose**: This document is the authoritative blueprint for writing Section 4 of the Sentinel Final Report.
> It maps every subsection to: its title, the narrative thread, the exact data to cite (from `combined_stats_for_report.md`),
> and the chart(s) or table(s) to include.
>
> **Data provenance note** (must appear as a paragraph at the start of Section 4):
> All multi-service statistics are drawn from three concurrent deployment instances (farhan, ben_1, ben_2)
> over a four-day evaluation window (April 15–18, 2026), unless explicitly marked ⚠️ single-instance.
> Latency measurements marked ⚠️ are from the local GPU-accelerated development machine only.

---

## Section 4 — Top-Level Structure

```
4  Results and Analysis
   4.1  Deployment Overview and Data Provenance
   4.2  Content Discovery and Deduplication (Ingestor)
   4.3  Web Scraping Performance and Reliability
   4.4  NLP Pipeline: Throughput and Content Analysis
   4.5  Processing Latency Analysis  ⚠️ single-instance
   4.6  Infrastructure Scalability
   4.7  End-to-End Pipeline Performance
```

---

## 4.1  Deployment Overview and Data Provenance

**Purpose**: Set the scene for the entire results section. Establish credibility through scale
and explain the multi-instance measurement setup.

**Narrative**:
- Three independent deployment instances ran simultaneously over April 15–18, 2026.
- Instance names: farhan (primary, GPU), ben_1, ben_2.
- Combined, they processed the full background corpus pipeline.
- This section uses combined statistics except where marked with a ⚠️ local-device footnote.
- Establish the pipeline funnel: 203,244 RSS entries → 1,431 scraped → 4,353 NLP-processed.

**Key numbers to state**:
- 203,244 raw RSS feed entries ingested
- 1,431 net-new articles forwarded for scraping (99.3% filtered)
- 7,518 scraping jobs executed across three instances
- 4,353 NLP-processed articles
- 24,252 claims extracted; 138,193 named entities identified

**Chart to include**:
- **`chart_v2_pipeline_funnel.png`** — full-width, shows the 5-stage funnel with percentage
  drop at each stage. Caption: *"Figure 4.1: End-to-end pipeline throughput funnel across three
  deployment instances, April 15–18, 2026. Each stage label shows the absolute count and
  percentage retained from the previous stage."*

**Tables**: None required — the funnel chart embeds all values.

**Cross-references**: Section 3 methodology for pipeline design; Sections 4.2–4.4 for detail.

---

## 4.2  Content Discovery and Deduplication (Ingestor)

**Purpose**: Demonstrate the scale and efficiency of the ingestor's deduplication mechanism.
Two sub-findings: (a) massive deduplication rate at scale, (b) near-perfect consistency across
the long-running deployment.

**Narrative**:
1. **Daily volume and dedup efficiency** — The ingestor polled 157 RSS feeds across 8 outlets.
   Volume increased 4.5× from Apr 15 to Apr 17 as polling frequency increased; Apr 18 dropped
   to near-zero as evaluation ended. Despite volume spikes, the deduplication rate held steady at
   98.1–99.4%, confirming the Redis-based seen-URL set scales proportionally with corpus size.

2. **Long-run validation** — Over 27 prior days (Feb 25 – Apr 12), the ingestor processed
   3,661,818 URLs and discovered 24,293 new articles (~900/day), deduplicating 98.3%.
   This confirms the dedup mechanism remains effective over weeks, not just days.

3. **Per-outlet dedup** — Guardian had the lowest dedup rate (96.8%) and highest new-article
   yield, consistent with its position as a high-volume breaking news outlet. NPR and CBC
   had 100% dedup rates in sample cycle — their content is stable and frequently recirculated.

**Key numbers**:
- Per-day raw: Apr15=20,755 / Apr16=81,685 / Apr17=94,102 / Apr18=6,702
- Per-day new: Apr15=59 / Apr16=464 / Apr17=907 / Apr18=1
- April dedup rate: 98.6% average (range 98.1–99.4%)
- Long-run (27 days): 3,661,818 URLs → 24,293 new (98.3% dedup, ~900 new/day)

**Charts to include**:
- **`chart_r1_ingestor_volume.png`** *(PRIMARY)* — dual-axis bar+line: daily raw volume (bars)
  vs new articles forwarded (line). Caption: *"Figure 4.2: Daily RSS volume processed (bars,
  left axis) versus net-new articles forwarded to the scraper (line, right axis). The persistent
  gap between bars and line reflects the deduplication filter retaining 98.1–99.4% of entries."*

**Tables to include**:
- **Table 4.2** — Inline 4-row table:

  | Date | Raw RSS Entries | After Dedup | New Forwarded | Dedup Rate |
  |------|----------------|-------------|---------------|------------|
  | Apr 15 | 20,755 | 10,254 | 59 | 99.4% |
  | Apr 16 | 81,685 | 40,492 | 464 | 98.9% |
  | Apr 17 | 94,102 | 46,906 | 907 | 98.1% |
  | Apr 18 | 6,702 | 3,347 | 1 | 100.0% |

  Caption: *"Table 4.2: Ingestor daily deduplication statistics, April 15–18, 2026 (combined
  three instances)."*

**Discussion point**: The 4.4× increase from Apr 15 to Apr 17 tests the ingestor's ability to
scale gracefully under increased polling load. The consistent dedup rate (variance < 1.3%)
under this volume increase demonstrates that the Redis-set-based dedup mechanism scales
O(1) per lookup regardless of corpus size.

---

## 4.3  Web Scraping Performance and Reliability

**Purpose**: Two distinct findings — (a) progressive error rate degradation consistent with IP
throttling/rate-limiting, (b) per-outlet variability showing that latency and error rate are
independent, pointing to different failure modes per outlet.

**Narrative**:
1. **Overall statistics** — 7,518 jobs processed, 4,169 successful (55.5% success rate),
   3,349 errors (44.5% overall error rate). Average latency 72.2s/article. Downloaded 3.37 GB
   of raw HTML, extracting 23 MB of article text (146.6× compression ratio).

2. **Daily error rate escalation** — Error rate rose monotonically from 30.8% (Apr 15) to
   95.7% (Apr 18) while average latency showed no corresponding trend (77.1s → 78.3s → 57.7s
   → 90.6s). The decoupling of error rate from latency is the key finding: the failures are not
   due to slow network responses (which would also increase latency) but to server-side
   rejection of requests — consistent with progressive IP rate-limiting over the deployment period.

3. **Per-outlet scatter analysis** — ABC exemplifies the anti-scraping hypothesis: fast page
   loads (22.8s avg) but 84.8% error rate, suggesting immediate bot-detection rejection rather
   than slow content delivery. NPR shows the inverse: highest latency (127.5s) but lowest
   error rate (26.8%), indicating full page rendering is required but eventually succeeds.
   Guardian and BBC cluster together (moderate latency ~63–96s, moderate error ~33–36%),
   consistent with standard anti-bot measures.

4. **Error type breakdown** — ValueError (87.2%) dominates, indicating HTML structural
   changes that the content parser cannot accommodate. ReadTimeoutErrors (2.2%) represent
   genuine network failures. AttributeError (8.5%) suggests DOM elements the scraper expects
   are absent — consistent with A/B page variations or CDN-delivered alternate layouts.

**Key numbers**:
- Total: 7,518 jobs; 4,169 success (55.5%); 3,349 errors (44.5%)
- Daily error %: 30.8% / 32.4% / 58.8% / 95.7%
- Daily latency: 77.1s / 78.3s / 57.7s / 90.6s
- Per-outlet: ABC(84.8%, 22.8s), NPR(26.8%, 127.5s), NBC(59.9%, 88.6s), Guardian(32.9%, 95.9s)
- HTML downloaded: 3.37 GB; text extracted: 23 MB; ratio: 146.6× avg
- Error types: ValueError 87.2%, AttributeError 8.5%, ReadTimeout 2.2%, TypeError 0.9%

**Charts to include**:
- **`chart_r2_scraper_error_trend.png`** *(PRIMARY)* — dual-axis line: error rate (red) vs
  latency (grey dashed). Caption: *"Figure 4.3a: Web scraper daily error rate (red, left axis)
  and average latency (grey, right axis) over the evaluation period. The monotonic rise in error
  rate despite stable latency is consistent with progressive IP-based rate-limiting by target
  servers."*

- **`chart_r3_scraper_scatter.png`** *(PRIMARY)* — scatter plot, one point per outlet.
  Caption: *"Figure 4.3b: Per-outlet scraping error rate versus average latency. The absence
  of positive correlation (ABC: fast + high error; NPR: slow + low error) demonstrates that
  scraping failure is driven by server-side anti-bot measures rather than network latency."*

**Tables to include**:
- **Table 4.3** — Per-outlet summary table (7 columns: Outlet, Jobs, Success, Error Rate,
  Avg Latency, HTML Downloaded, HTML/Text Ratio):

  | Outlet | Jobs | Success | Error Rate | Avg Latency | Key observation |
  |--------|------|---------|------------|-------------|-----------------|
  | ABC | ~301 | 15.2% | 84.8% | 22.8s | Fast load, near-total rejection |
  | NPR | ~502 | 73.2% | 26.8% | 127.5s | Slow render, high success |
  | NBC | ~199 | 40.1% | 59.9% | 88.6s | — |
  | CBC | ~233 | 54.8% | 45.2% | 69.1s | — |
  | Euronews | ~301 | 54.2% | 45.8% | 39.9s | — |
  | CBS | ~543 | 63.8% | 36.2% | 69.2s | — |
  | BBC | ~1,111 | 63.8% | 36.2% | 63.0s | — |
  | Guardian | ~1,158 | 67.1% | 32.9% | 95.9s | Highest article volume |

  Caption: *"Table 4.3: Web scraper per-outlet performance metrics (combined three instances,
  April 15–18, 2026). Error rate and latency are not correlated, pointing to outlet-specific
  anti-bot policies as the dominant failure driver."*

**Discussion point**: Per-instance variance in error rate (farhan/ben_1 ~53% vs ben_2 ~19%)
suggests geographic or network-level differences in rate-limiting exposure, which has
implications for distributed scraping architecture in future deployments.

---

## 4.4  NLP Pipeline: Throughput and Content Analysis

**Purpose**: Demonstrate the NLP pipeline's analytical output at scale. Three sub-findings:
(a) claim/entity extraction at scale, (b) per-outlet content density variation,
(c) bias and sentiment corpus characterisation.

### 4.4.1  Claim and Entity Extraction at Scale

**Narrative**: The pipeline processed 4,353 articles, extracting 24,252 check-worthy claims
(avg 5.6/article) and 138,193 named entities (avg 31.7/article). Near-identical throughput
across the three independent instances (1,559 / 1,557 / 1,237 articles) with ≤2% variance in
bias classification confirms the stateless pipeline scales horizontally.

**Key numbers**:
- 4,353 total articles; instance split: 1,559 / 1,557 / 1,237
- 24,252 claims total; avg 5.6/article; range 5.5–6.0 per day
- 138,193 entities; avg 31.7/article
- Entity type: PER 36.5% / ORG 25.5% / LOC 21.9% / MISC 16.1%

**Chart**: **`chart_v2_nlp_entity_types.png`** — entity type donut/bar.
Caption: *"Figure 4.4a: Distribution of 138,193 named entities by type across the combined
production corpus. Person entities (PER) are the most frequent type at 36.5%, reflecting the
person-centric framing of news articles."*

**Table**:
- **Table 4.4a** — Entity type breakdown (Type | Count | %)

### 4.4.2  Per-Outlet Content Density

**Narrative**: CBS produced significantly fewer claims/article (3.6) and entities/article (13.7)
than all other outlets, suggesting shorter or more opinion-based articles. Euronews had the
highest claim density (7.0/article); NPR had the highest entity density (38.3/article). This
outlet-level variation has practical implications: a uniform check-worthiness threshold may
over-filter CBS articles and under-filter Euronews. Outlet-adaptive thresholds are a future
enhancement.

**Key numbers**: See per-outlet table from combined_stats_for_report.md section 1.3.

**Chart**: **`chart_r5_outlet_density.png`** *(PRIMARY)*
Caption: *"Figure 4.4b: Per-outlet content density. CBS is a consistent outlier with markedly
lower claim (3.6) and entity (13.7) density per article. Euronews leads on claim density (7.0)
and NBC/NPR lead on entity density (38–39 per article)."*

### 4.4.3  Political Bias and Sentiment Distribution

**Narrative**: Across all three instances, 62.0% of articles were classified as Left-leaning,
26.1% Center, 11.9% Right (premsa/political-bias-prediction-allsides-BERT, F1=0.904).
The per-instance variance is ≤2%, confirming model determinism. The corpus left-skew is
a *source selection effect* — the eight active outlets (BBC, Guardian, CBC, NPR, etc.) are
predominantly centre-left publications. Sentiment was predominantly neutral (66%), with
negative (22%) substantially outweighing positive (12%) — a 1.83:1 ratio consistent with
documented negativity bias in mainstream news journalism.

**Key numbers**:
- Bias: Left 62.0% / Center 26.1% / Right 11.9%; ≤2% cross-instance variance
- Sentiment: Neutral 66% / Negative 22% / Positive 12%

**Chart**: **`chart_r6_bias_sentiment_donuts.png`** *(PRIMARY)*
Caption: *"Figure 4.4c: Political bias (left donut) and sentiment (right donut) distributions
across the combined production corpus (n=4,353 articles). Left-leaning dominance reflects
the political orientation of the selected RSS sources rather than classifier bias."*

### 4.4.4  Topic Distribution

**Narrative**: The zero-shot topic classifier assigned 9 topic labels. World (1,329), Politics
(1,065), and Health (856) together account for 40.0% of the corpus, reflecting the prominent
coverage themes of the evaluation period. 1,720 articles (21.6%) received the fallback
"General" label, indicating content the classifier could not confidently assign — primarily
human-interest and mixed-topic articles. This fallback rate is acceptable and expected for
a zero-shot approach without fine-tuning on news-specific topic taxonomies.

**Key numbers**:
- General=1,720 (21.6%), World=1,329 (16.7%), Politics=1,065 (13.4%),
  Health=856 (10.8%), Sports=805 (10.1%), Technology=614 (7.7%),
  Business=561 (7.1%), Science=426 (5.4%), Entertainment=364 (4.6%)

**Chart**: **`chart_r7_topic_distribution.png`** *(PRIMARY)*
Caption: *"Figure 4.4d: Topic distribution across the production corpus (n=7,740 articles
from DB query). The 'General' category (grey) represents the fallback label for articles
below the cosine-similarity confidence threshold. Named topic distribution is led by World
(17.2%), Politics (13.8%), and Health (11.1%)."*

---

## 4.5  Processing Latency Analysis ⚠️ Single-Instance (Local GPU)

**Purpose**: Characterise pipeline throughput at the component level. Identify the
Decontextualiser as the dominant bottleneck (78% of NLP time). Present retrieval latency.
Clearly scope all measurements as single-device, GPU-accelerated.

> ⚠️ **Note**: All latency figures in this section were measured on a single local GPU-accelerated
> deployment (NVIDIA GPU, CUDA 12.4). CPU-only deployments will experience significantly
> higher NLP latency due to the transformer-heavy Decontextualiser stage.

### 4.5.1  NLP Stage-Level Latency

**Narrative**: Mean NLP latency was 24.3s/article (median 20.1s, P95 27.9s, n=524). The
tight P90/P95 spread (24.9s / 27.9s) relative to the mean indicates highly consistent
throughput with the high max (877s) being a cold-start GPU artefact. Stage 4
(Decontextualiser) accounts for a disproportionate 19.0s (78%) of total latency, running three
transformer models per sentence (MixQG, RoBERTa-SQuAD2, Flan-T5) in sequence.
All remaining eight stages collectively contribute under 5.5 seconds. Disabling the
Decontextualiser would reduce per-article latency from ~24s to ~5s (a 5× speedup) at the cost
of reduced claim self-containedness for retrieval.

**Key numbers**:
- Mean 24.3s; Median 20.1s; P90 24.9s; P95 27.9s (n=524)
- Decontextualiser: 19.0s mean = 78% of total
- All others combined: ~5.3s total

**Chart**: **`chart_r4_nlp_stage_latency.png`** *(PRIMARY)*
Caption: *"Figure 4.5a: NLP pipeline per-stage mean processing latency (local GPU, n=524).
The Decontextualiser (Stage 4) dominates at 19.0s, representing 78% of total processing time.
All other stages collectively process in under 5.5 seconds."*

**Table 4.5a** — Full stage breakdown:

| Stage | Mean | Median | % of Total |
|-------|------|--------|-----------|
| Decontextualiser (Stage 4) | 19.0s | 16.9s | ~78% |
| Sentence Extraction (Stage 3) | 3.0s | 1.3s | ~12% |
| Entity Recognizer (Stage 2) | 1.2s | 0.9s | ~5% |
| Check-Worthiness (Stage 5) | 0.3s | 0.3s | ~1% |
| Topic Classifier (Stage 9) | 0.3s | 0.1s | ~1% |
| Bias Detector (Stage 8) | 0.2s | 0.2s | ~1% |
| Embedder (Stage 6) | 0.2s | 0.2s | ~1% |
| Preprocessor (Stage 1) | 0.1s | 0.1s | <1% |

Caption: *"Table 4.5a: NLP pipeline per-stage latency breakdown (local GPU, n=524 articles).
All measurements are single-instance and should not be treated as representative of
CPU-only deployments."*

### 4.5.2  Retrieval Layer Latency

**Narrative**: Mean retrieval latency was 22.1s/article (median 20.8s, P95 41.5s, n=456
background jobs). This includes pgvector HNSW similarity search across all stored claims,
NLI re-ranking via cross-encoder (typeform/distilbert-base-uncased-mnli), and PostgreSQL
persistence. The P95 tail (41.5s) is noticeably higher than the mean, reflecting corpus-size
sensitivity in the vector search as the database grew over the evaluation period.

**Key numbers**:
- Mean 22.1s; Median 20.8s; P90 34.4s; P95 41.5s (n=456)

**Chart**: **`chart_v2_retrieval_latency.png`** — latency percentile bar chart.
Caption: *"Figure 4.5b: Retrieval layer processing latency distribution (local GPU, n=456
background jobs). The elevated P90/P95 tail relative to the median reflects increasing corpus
size over the evaluation window, as the HNSW index searches against a larger set of stored
claims."*

---

## 4.6  Infrastructure Scalability

**Purpose**: Quantify storage growth and derive forward projections. Motivate the Redis TTL
recommendation with concrete numbers.

**Narrative**: PostgreSQL grew from 585 MB to 1.26 GB over 47 hours (+676 MB, 14.1 MB/hr).
Redis grew from 504 MB to 2.32 GB over the same period (+1.82 GB, 40.8 MB/hr) — growing
2.9× faster than PostgreSQL. Redis growth is driven primarily by the seen-URL deduplication
sets, which carry no expiry and grow unboundedly. At the observed 40.8 MB/hr rate, a typical
8 GB free-tier Redis instance would be exhausted in approximately 9 days of continuous
operation. This makes TTL-based pruning of the seen-URL sets a required production
enhancement rather than an optional optimisation.

Extrapolating from PostgreSQL: at 14.1 MB/hr, continuous production operation would require
~340 MB/day, ~10 GB/month, or ~120 GB/year — manageable with any cloud-managed
PostgreSQL service but requiring a data retention and archiving policy at the 12-month horizon.

**Key numbers**:
- PostgreSQL: 585 MB → 1.26 GB; +14.1 MB/hr; ~10 GB/month projected
- Redis: 504 MB → 2.32 GB; +40.8 MB/hr; 8 GB free tier exhausted in ~9 days
- Redis grows 2.9× faster than PostgreSQL

**Chart**: **`chart_r8_db_growth.png`** *(PRIMARY)*
Caption: *"Figure 4.6: PostgreSQL (blue) and Redis (red) storage growth over the evaluation
window. Redis grows approximately 2.9× faster than PostgreSQL (40.8 MB/hr vs 14.1 MB/hr),
driven by the unbounded accumulation of seen-URL hashes in the deduplication sets."*

**Table 4.6** — Growth snapshot table:

| Timestamp | PostgreSQL | Redis |
|-----------|-----------|-------|
| Apr 15 15:32 | 585 MB | 504 MB |
| Apr 16 03:00 | 795 MB | 1,500 MB |
| Apr 16 15:00 | 1,030 MB | 1,990 MB |
| Apr 17 03:00 | 1,213 MB | 2,160 MB |
| Apr 17 14:00 | 1,261 MB | 2,320 MB |

Caption: *"Table 4.6: Storage growth over the 47-hour measurement window. Redis memory
growth is driven by unbounded accumulation in the seen-URL deduplication sets."*

---

## 4.7  End-to-End Pipeline Performance

**Purpose**: Synthesise all per-service latency figures into a single E2E summary. Contextualise
the 2-minute/article figure against the asynchronous architecture's design intent.

**Narrative**: The full background pipeline — from URL submission to persisted analysis —
completes in approximately 118.6 seconds (~2 minutes) per article on GPU-accelerated
hardware. Web scraping (72.2s, 61%) is the dominant cost, driven by Selenium-rendered
dynamic page loading. The NLP pipeline (24.3s, 20%) and Retrieval Layer (22.1s, 19%)
contribute nearly equally at the downstream end. The 2-minute figure is acceptable for the
asynchronous background pipeline, which processes articles in batch without any user
waiting. For the on-demand pipeline, this E2E latency is the user-perceived response time,
making the web scraper the highest-value target for future optimisation.

The pipeline funnel demonstrates overall efficiency: 99.3% of RSS entries are eliminated by
deduplication before any network request is made, and 55.5% of attempted scrapes succeed
and flow uninterrupted through NLP and Retrieval.

**Key numbers**:
- Scraper: 72.2s (61% of E2E)
- NLP: 24.3s (20%)
- Retrieval: 22.1s (19%)
- Total: ~118.6s ≈ 2 minutes/article

**Charts to include**:
- **`chart_r9_e2e_latency.png`** *(PRIMARY)* — stacked horizontal bar: 3 segments.
  Caption: *"Figure 4.7a: End-to-end pipeline latency breakdown per article on GPU-accelerated
  hardware. Web scraping (72.2s) accounts for 61% of total processing time, with NLP and
  Retrieval contributing 20% and 19% respectively. ⚠️ NLP and Retrieval figures are single-instance
  measurements; scraping latency is drawn from the combined three-instance dataset."*

- **`chart_v2_pipeline_funnel.png`** *(may be cross-referenced from 4.1 here, or repeated)*

---

## Chart Usage Summary

| Chart file | Section | Figure label | Type |
|---|---|---|---|
| `chart_v2_pipeline_funnel.png` | 4.1 | Figure 4.1 | Funnel — PRIMARY |
| `chart_r1_ingestor_volume.png` | 4.2 | Figure 4.2 | Dual-axis bar+line — PRIMARY |
| `chart_r2_scraper_error_trend.png` | 4.3 | Figure 4.3a | Dual-axis line — PRIMARY |
| `chart_r3_scraper_scatter.png` | 4.3 | Figure 4.3b | Scatter — PRIMARY |
| `chart_v2_nlp_entity_types.png` | 4.4.1 | Figure 4.4a | Bar/donut |
| `chart_r5_outlet_density.png` | 4.4.2 | Figure 4.4b | Grouped bar — PRIMARY |
| `chart_r6_bias_sentiment_donuts.png` | 4.4.3 | Figure 4.4c | Dual donut — PRIMARY |
| `chart_r7_topic_distribution.png` | 4.4.4 | Figure 4.4d | Horizontal bar — PRIMARY |
| `chart_r4_nlp_stage_latency.png` | 4.5.1 | Figure 4.5a | Horizontal bar — PRIMARY |
| `chart_v2_retrieval_latency.png` | 4.5.2 | Figure 4.5b | Percentile bar |
| `chart_r8_db_growth.png` | 4.6 | Figure 4.6 | Dual line — PRIMARY |
| `chart_r9_e2e_latency.png` | 4.7 | Figure 4.7a | Stacked bar — PRIMARY |

**Not included in Results section** (can go in Appendix or omit):
- `chart_v2_scraper_error_types.png` — error type breakdown (covered by Table 4.3 inline)
- `chart_v2_nlp_bias_distribution.png` — superseded by `chart_r6`
- `chart_v2_sentiment_distribution.png` — superseded by `chart_r6`
- `chart_v2_ingestor_daily_volume.png` — superseded by `chart_r1`
- `chart_v2_ingestor_longrun.png` — can be used in 4.2 as a supplementary figure
- `chart_v2_nlp_outlet_claims.png` — superseded by `chart_r5`
- `chart_v2_nlp_daily_throughput.png` — optional supplement in 4.4.1
- `chart_v2_retrieval_verdicts.png` — local-only (10 user jobs); omit from Results
- `chart_v2_scraper_outlet_latency.png` — superseded by `chart_r3`
- `chart_v2_db_growth.png` — superseded by `chart_r8`

---

## Tables Summary

| Table | Section | Content |
|---|---|---|
| Table 4.2 | 4.2 | Ingestor daily deduplication (4 rows × 5 cols) |
| Table 4.3 | 4.3 | Per-outlet scraper metrics (8 rows × 5 cols) |
| Table 4.4a | 4.4.1 | Entity type distribution (4 rows × 3 cols) |
| Table 4.5a | 4.5.1 | NLP per-stage latency (8 rows × 4 cols) |
| Table 4.6 | 4.6 | Storage growth snapshot (5 rows × 3 cols) |

---

## Key Analytical Findings (to be stated explicitly in Results)

1. **Deduplication at scale**: The ingestor filters 99.3% of RSS content before any scraping
   request, making deduplication-first architecture essential for pipeline efficiency.

2. **Scraper degradation**: Progressive error rate rise (31% → 96% over 4 days) with flat
   latency is consistent with IP-based rate-limiting. Failure modes differ by outlet — ABC
   rejects quickly, NPR succeeds slowly.

3. **Horizontal NLP scalability**: Three independent instances achieved near-identical
   throughput (1,237–1,559 articles) and ≤2% bias classification variance, confirming
   the stateless NLP pipeline scales without coordination overhead.

4. **Decontextualiser bottleneck**: One stage accounts for 78% of NLP latency. Its removal
   would yield a 5× speedup at the cost of claim self-containedness.

5. **Corpus characterisation**: The bias skew (Left 62%) is a *source selection* effect, not
   a model artefact. Sentiment negativity dominance (22% vs 12% positive) cross-validates
   documented media negativity bias.

6. **Redis TTL urgency**: At 40.8 MB/hr unbounded growth, the seen-URL sets will exhaust
   an 8 GB Redis instance within ~9 days. TTL pruning is a required production enhancement.

7. **E2E throughput**: The system processes one article end-to-end in ~2 minutes on GPU
   hardware, with web scraping (61%) as the dominant cost — the highest-value optimisation target.

---

## Writing Notes

- **Tone**: State findings factually before interpreting. E.g. "The error rate rose from X to Y.
  This is consistent with IP-based rate-limiting, as..." rather than starting with the interpretation.
- **Data provenance**: Always distinguish multi-instance (data_report) from single-instance (logs).
  Use "⚠️ single-device measurement" notation in figure captions.
- **Cross-references**: Section 4.3 should cross-reference Section 3.2.3 (Web Scraper methodology)
  when discussing the cascading extraction strategy. Section 4.5 should cross-reference 3.2.4.5
  (Decontextualiser methodology) when discussing the 78% latency share.
- **Figure numbering**: Use 4.1, 4.2, 4.3a, 4.3b, etc. (renumber to fit the report's actual figure
  count if needed — some figures appear in the Methodology section already).
- **Word budget guidance**: 4.2 (Ingestor) ~300 words; 4.3 (Scraper) ~400 words;
  4.4 (NLP) ~500 words; 4.5 (Latency) ~350 words; 4.6 (Infrastructure) ~250 words;
  4.7 (E2E) ~200 words. Total ~2,200 words for Section 4.
