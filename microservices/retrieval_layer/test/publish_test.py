import json
from datetime import datetime
from common.redis_client.connection import redis_connection

r = redis_connection.get_client()

header = {
    "job_id": "test-1",
    "type": "user",
    "uid": "unique-id-123",
    "status": "pending",
    "created_at": datetime.now().isoformat()
}

payload = {
    "article_url": "https://example.com/article",
    "news_outlet": "Example News",
    "title": "Test Article Title",
    "publish_date": datetime.now().isoformat(),
    "author": "Test Author",
    "summary": "Test summary",
    "raw_html": "<html><body>Test</body></html>",
    "parsed_text": "This is the parsed text of the article.",
    "sentences": [],
    "claims_in_article": [],
    "entities_in_article": [],
    "bias_profile": None
}

stage_timestamps = [
    {
        "job_uid": "unique-id-123",
        "stage_name": "scraped",
        "wall_time": datetime.now().isoformat(),
        "offset_s": 0.0
    }
]

# Publish with separate fields
fields = {
    "header": json.dumps(header),
    "payload": json.dumps(payload),
    "stage_timestamps": json.dumps(stage_timestamps)
}

stream = "user:to.be.retrieval"
res = r.xadd(stream, fields)

print("xadd id:", res)