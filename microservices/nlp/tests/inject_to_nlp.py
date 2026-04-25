"""
Inject an article JSON file directly into the NLP service's Redis input stream.

The article JSON must be in the same format as the files in debug_articles/:
    article_url     — source URL
    article_title   — article headline
    article_text    — full article body
    article_summary — (optional) summary text
    source / news_outlet — (optional) outlet name

By default this targets the user:to.be.nlp stream on localhost:6379.
Override with REDIS_HOST / REDIS_PORT env vars.

Usage:
    python microservices/nlp/tests/inject_to_nlp.py
    REDIS_HOST=localhost python microservices/nlp/tests/inject_to_nlp.py
"""

import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import redis

# ---------------------------------------------------------------------------
# CONFIGURE: point this at the article JSON you want to inject
# ---------------------------------------------------------------------------
file = Path(__file__).parent / "debug_articles" / "bbc_001.json"
# ---------------------------------------------------------------------------

STREAM = os.getenv("NLP_INPUT_STREAM", "user:to.be.nlp")
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))


def load_article(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_message(data: dict) -> dict:
    """Build a Message dict in the exact format the NLP service expects."""
    return {
        "header": {
            "uid": str(uuid.uuid4()),
            "type": "user",
            "status": "scraped",
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
        "payload": {
            "article_url": data.get("article_url") or data.get("url", ""),
            "news_outlet": data.get("news_outlet") or data.get("source", ""),
            "title": data.get("article_title", ""),
            "parsed_text": data.get("article_text", ""),
            "summary": data.get("article_summary", ""),
        },
        "stage_timestamps": [],
    }


def main():
    article_path = Path(file)
    if not article_path.exists():
        print(f"ERROR: article file not found: {article_path}", file=sys.stderr)
        sys.exit(1)

    data = load_article(article_path)
    message = build_message(data)

    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT)
    try:
        r.ping()
    except redis.ConnectionError as e:
        print(
            f"ERROR: cannot connect to Redis at {REDIS_HOST}:{REDIS_PORT} — {e}",
            file=sys.stderr,
        )
        sys.exit(1)

    redis_id = r.xadd(STREAM, {"payload": json.dumps(message)})

    print(f"Injected article into {STREAM}")
    print(
        f"  Redis ID : {redis_id.decode() if isinstance(redis_id, bytes) else redis_id}"
    )
    print(f"  Job UID  : {message['header']['uid']}")
    print(f"  Title    : {message['payload']['title'][:80]}")
    print(f"  Outlet   : {message['payload']['news_outlet']}")
    print(f"  URL      : {message['payload']['article_url']}")


if __name__ == "__main__":
    main()
