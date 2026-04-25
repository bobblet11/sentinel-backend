"""
Fetch one representative article from each of 8 news sources via their RSS feeds.
Full article text is extracted using trafilatura (no Selenium required).
Output: tests/debug_articles/{source_slug}_001.json per source.

Run from workspace root:
    python tests/debug_articles/fetch_articles.py
"""

import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import feedparser
import requests
import trafilatura

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

OUTPUT_DIR = Path(__file__).parent
REQUEST_TIMEOUT = 20  # seconds per HTTP request
MIN_TEXT_LENGTH = 200  # discard articles shorter than this

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("fetch_articles")

SOURCES = [
    {
        "slug": "bbc",
        "name": "BBC News",
        "bias": "Neutral/UK",
        "rss": "https://feeds.bbci.co.uk/news/world/rss.xml",
    },
    {
        "slug": "fox",
        "name": "Fox News",
        "bias": "Right-leaning US",
        "rss": "https://moxie.foxnews.com/google-publisher/politics.xml",
    },
    {
        "slug": "msnbc",
        "name": "MSNBC",
        "bias": "Left-leaning US",
        "rss": "https://feeds.nbcnews.com/msnbc/public",
    },
    {
        "slug": "ap",
        "name": "AP News",
        "bias": "Neutral/Wire",
        "rss": "https://feeds.apnews.com/rss/apf-topnews",
    },
    {
        "slug": "guardian",
        "name": "The Guardian",
        "bias": "Left-leaning UK",
        "rss": "https://www.theguardian.com/world/rss",
    },
    {
        "slug": "reuters",
        "name": "Reuters",
        "bias": "Neutral/Wire",
        "rss": "https://feeds.reuters.com/reuters/topNews",
    },
    {
        "slug": "aljazeera",
        "name": "Al Jazeera",
        "bias": "Middle East/Global",
        "rss": "https://www.aljazeera.com/xml/rss/all.xml",
    },
    {
        "slug": "euronews",
        "name": "Euronews",
        "bias": "Neutral/European",
        "rss": "https://www.euronews.com/rss",
    },
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def fetch_rss(rss_url: str) -> list:
    """Return a list of feedparser entries from an RSS URL."""
    try:
        feed = feedparser.parse(rss_url, agent=HEADERS["User-Agent"])
        if feed.bozo:
            log.warning(f"  RSS parse warning for {rss_url}: {feed.bozo_exception}")
        return feed.entries
    except Exception as exc:
        log.error(f"  RSS fetch failed for {rss_url}: {exc}")
        return []


def fetch_full_text(url: str) -> Optional[str]:
    """Download a page and extract clean body text with trafilatura."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        raw_html = resp.text
    except Exception as exc:
        log.warning(f"    HTTP error fetching {url}: {exc}")
        return None

    text = trafilatura.extract(
        raw_html,
        include_comments=False,
        include_tables=False,
        no_fallback=False,
    )
    return text if text and len(text) >= MIN_TEXT_LENGTH else None


def pick_best_entry(entries: list) -> Optional[dict]:
    """
    Walk RSS entries until we find one where trafilatura can extract text.
    Returns a dict with keys: url, title, summary, text.
    """
    for entry in entries[:15]:  # try up to 15 entries per source
        url = getattr(entry, "link", None)
        if not url:
            continue

        title = getattr(entry, "title", "")
        summary = getattr(entry, "summary", "") or ""

        log.info(f"    Trying: {url}")
        text = fetch_full_text(url)
        if text:
            return {
                "url": url,
                "title": title,
                "summary": summary,
                "text": text,
            }
        time.sleep(0.5)  # polite delay

    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def collect_and_save(source: dict) -> bool:
    slug = source["slug"]
    log.info(f"[{source['name']}] Fetching RSS: {source['rss']}")
    entries = fetch_rss(source["rss"])

    if not entries:
        log.error(f"[{source['name']}] No RSS entries found — skipping.")
        return False

    log.info(f"[{source['name']}] {len(entries)} RSS entries, scanning for full text…")
    article = pick_best_entry(entries)

    if not article:
        log.error(f"[{source['name']}] Could not extract text from any entry — skipping.")
        return False

    # Build output document matching the format used by test_pipeline.py
    doc = {
        "source": source["name"],
        "bias_profile": source["bias"],
        "url": article["url"],
        "article_url": article["url"],
        "article_title": article["title"],
        "article_summary": article["summary"],
        "article_text": article["text"],
        "word_count": len(article["text"].split()),
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "characteristics": {
            "bias": source["bias"],
            "length_category": (
                "short" if len(article["text"].split()) < 300
                else "medium" if len(article["text"].split()) < 800
                else "long"
            ),
        },
    }

    out_path = OUTPUT_DIR / f"{slug}_001.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2, ensure_ascii=False)

    log.info(
        f"[{source['name']}] Saved {doc['word_count']} words → {out_path.name}"
    )
    return True


def main():
    collected = 0
    failed = []
    for source in SOURCES:
        ok = collect_and_save(source)
        if ok:
            collected += 1
        else:
            failed.append(source["name"])
        time.sleep(1)  # polite pause between sources

    print(f"\n{'='*60}")
    print(f"Collection complete: {collected}/{len(SOURCES)} sources")
    if failed:
        print(f"Failed sources: {', '.join(failed)}")
    else:
        print("All sources collected successfully.")
    print(f"Articles saved to: {OUTPUT_DIR.resolve()}")
    print(f"{'='*60}")

    if collected < 5:
        log.error("Fewer than 5 articles collected — pipeline test may be unreliable.")
        sys.exit(1)


if __name__ == "__main__":
    main()
