import random
from typing import Any, Dict, List

from microservices.retrieval_layer.db.session import get_db_session
from microservices.retrieval_layer.processor import process_nlp_message
from microservices.retrieval_layer.retrieval.pipeline import retrieve_candidate_claims

EMBEDDING_DIM = 768


def random_embedding(dim: int) -> List[float]:
    return [random.uniform(-1.0, 1.0) for _ in range(dim)]


def build_dummy_nlp_payload() -> Dict[str, Any]:
    claim_text = "Government increased taxes"
    return {
        "article": {
            "url": f"https://dummy.local/article/{random.randint(1000, 9999)}",
            "title": "Dummy Article",
            "text": "A short dummy article about taxes and policy.",
            "html": "<p>Dummy article about taxes and policy.</p>",
            "publishedAt": "2026-02-23T00:00:00",
            "outlet_name": "Dummy Outlet",
        },
        "claims": [
            {
                "original_sentence": claim_text,
                "decontextualised_claim": claim_text,
                "decontextualised_embedding": random_embedding(EMBEDDING_DIM),
                "centrality_score": 0.9,
                "entities": [
                    {"name": "Government", "type": "ORG"},
                    {"name": "taxes", "type": "TOPIC"},
                ],
            }
        ],
    }


def main() -> None:
    db = get_db_session()

    # 1) Insert dummy NLP output into DB
    payload = build_dummy_nlp_payload()
    result = process_nlp_message(payload)
    print("Inserted article/claims:", result)

    # 2) Run retrieval against the same claim
    main_claim = payload["claims"][0]
    retrieval_results = retrieve_candidate_claims(
        db=db,
        claim_text=main_claim["decontextualised_claim"],
        claim_embedding=main_claim["decontextualised_embedding"],
        entities=[e["name"] for e in main_claim.get("entities", [])],
        top_k=5,
        run_nli=True,
    )

    print("\n=== RETRIEVAL RESULTS ===\n")
    for claim, score, label, confidence in retrieval_results:
        print(
            f"Claim ID: {claim['id']}\n"
            f"Text: {claim['decontextualised_claim']}\n"
            f"Similarity: {score:.4f}\n"
            f"NLI: {label} ({confidence:.2f})\n"
            "------------------------"
        )


if __name__ == "__main__":
    main()
