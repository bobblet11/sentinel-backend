# Ingestor Service

## What It Does

The ingestor service discovers new articles from monitored RSS feeds and pushes them into the lower-priority background pipeline.

## Main Responsibilities

- fetch RSS feeds from configured news sources
- identify candidate article URLs and metadata
- remove duplicates before they enter expensive downstream stages
- publish new articles to the scraping stream

## Key Design Points

- Designed as a background discovery component rather than a user-facing service.
- Uses concurrent feed fetching to improve throughput across many sources.
- Applies duplicate filtering before scraping to avoid wasting network and NLP compute.
- Maintains a persistent seen-URL mechanism so previously processed content does not re-enter the corpus.
- Supports outlet-aware ingestion through configured feed metadata and URL patterns.

## Interfaces

- input: RSS sources configured in `rss_feeds.json`
- output stream: typically `background:to.be.scraped`

## Important Files

- `main.py` for service entry
- `rss_ingestor.py` for RSS fetching and parsing
- `base_ingestor.py` for shared ingestion logic and stats handling
- `rss_feeds.json` for source configuration

