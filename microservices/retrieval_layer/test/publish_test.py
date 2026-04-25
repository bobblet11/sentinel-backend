import json
from datetime import datetime

from common.redis_client.connection import redis_connection

r = redis_connection.get_client()

full_message = {
    "header": {
        "id": 1,
        "type": "user",
        "uid": "unique-id-789",
        "status": "pending",
        "created_at": datetime.now().isoformat(),
    },
    "payload": {
        "article_url": "https://example.com/article3",
        "news_outlet": "Example News",
        "title": "Test Article Title",
        "publish_date": datetime.now().isoformat(),
        "author": "Test Author",
        "summary": "Test summary",
        "raw_html": "<html><body>Test</body></html>",
        "parsed_text": "This is the parsed text of the article.",
        "sentences": [],
        "claims_in_article": [
            {
                "decontextualised_claim_text": "Government raised taxes",
                "decontextualised_claim_embedding": [0.01] * 768,
                "confidence": 0.8,
                "source_sentence_indices": [0],
                "NER_entities": [
                    {
                        "entity_text": "government",
                        "type_of_entity": "ORG",
                        "start_char": 4,
                        "end_char": 14,
                    },
                    {
                        "entity_text": "taxes",
                        "type_of_entity": "TOPIC",
                        "start_char": 22,
                        "end_char": 27,
                    },
                ],
            }
        ],
        "entities_in_article": [],
        "bias_profile": {
            "bias_category": "center",
            "bias_analysis_confidence": 0.9,
            "sentiment_category": "neutral",
            "sentiment_analysis_confidence": 0.95,
        },
    },
    "stage_timestamps": [
        {
            "job_uid": "unique-id-789",
            "stage_name": "scraped",
            "wall_time": datetime.now().isoformat(),
            "offset_s": 0.0,
        }
    ],
}

fields = {"payload": json.dumps(full_message)}

stream = "user:to.be.retrieval"
res = r.xadd(stream, fields)
print("xadd id:", res)
