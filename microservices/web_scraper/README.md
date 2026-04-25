# Web Scraper Service

## What It Does

The web scraper service consumes article jobs, fetches page content from source URLs, extracts readable article text, and forwards the enriched payload to the NLP stage.

## Main Responsibilities

- consume user and background scrape jobs from Redis Streams
- retrieve HTML from source pages
- parse and normalize article text from raw page content
- preserve enough metadata for downstream NLP processing
- route failures into failure streams instead of dropping them silently

## Key Design Points

- Uses browser-based fetching to handle JavaScript-heavy news sites.
- Supports retry logic with exponential backoff for unstable fetches.
- Separates fetch and parse responsibilities so extraction strategies can evolve independently.
- Uses outlet-aware parsing when possible, with fallback extraction paths when site-specific logic fails.
- Preserves operational visibility through explicit failure routing and scraper-side statistics.

## Interfaces

- input streams: `user:to.be.scraped`, `background:to.be.scraped`
- output streams: `user:to.be.nlp`, `background:to.be.nlp`

## Important Files

- `main.py` for service startup
- `scraper_service.py` for the stream-consuming service implementation
- `managers/fetch_manager_selenium.py` for page retrieval
- `managers/parse_manager.py` for extraction and cleanup logic

