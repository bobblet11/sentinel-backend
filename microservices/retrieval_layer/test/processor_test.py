from pprint import pprint

from microservices.retrieval_layer.processor import process_nlp_message

SAMPLE_MESSAGE = {
    "article": {
        "url": "https://example.com/news/1",
        "title": "Example news",
        "text": "Full article text here",
        "html": "<html>...</html>",
        "publishedAt": "2026-02-03T12:00:00",
        "outlet_name": "Example News",
        "sentiment": {
            "bias_category": "center",
            "bias_analysis_confidence": 0.9,
            "sentiment_category": "neutral",
            "sentiment_analysis_confidence": 0.95
        }
    },
    "claims": [
        {
            "original_sentence": "The government increased taxes last year.",
            "decontextualised_claim": "Government increased taxes last year",
            "decontextualised_embedding": [0.01, 0.02, 0.03],
            "centrality_score": 0.8,
            "entities": [{"name": "Government", "type": "ORG"}, {"name": "taxes", "type": "TOPIC"}]
        },
        {
            "original_sentence": "The ministry reported 5% growth.",
            "decontextualised_claim": "Ministry reported 5% growth",
            "decontextualised_embedding": [0.1, 0.2, 0.3],
            "centrality_score": 0.6,
            "entities": [{"name": "Ministry", "type": "ORG"}]
        }
    ]
}

if __name__ == "__main__":
    res = process_nlp_message(SAMPLE_MESSAGE)
    pprint(res)
