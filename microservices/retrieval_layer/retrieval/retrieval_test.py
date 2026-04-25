import random

from sqlalchemy.orm import Session

from microservices.retrieval_layer.db.models import Claim
from microservices.retrieval_layer.db.session import get_db_session
from microservices.retrieval_layer.retrieval.pipeline import retrieve_candidate_claims

EMBEDDING_DIM = 768  # MUST match pgvector column


def random_embedding(dim: int) -> list[float]:
    return [random.uniform(-1, 1) for _ in range(dim)]


def seed_fake_embeddings(db: Session, limit: int = 10):
    """
    Inject random embeddings into existing claims for testing only.
    """
    claims = db.query(Claim).limit(limit).all()

    if not claims:
        raise RuntimeError("No claims found in DB")

    for claim in claims:
        claim.decontextualised_embedding = random_embedding(EMBEDDING_DIM)

    db.commit()
    print(f"Seeded embeddings for {len(claims)} claims")


def main():
    db = get_db_session()

    # 1. Seed embeddings
    # seed_fake_embeddings(db)

    # 2. User input
    user_claim = "Government increased taxes"
    user_embedding = random_embedding(EMBEDDING_DIM)

    # 3. Run full pipeline
    results = retrieve_candidate_claims(
        db=db,
        claim_text=user_claim,
        claim_embedding=user_embedding,
        entities=["Government", "taxes"],
        top_k=3,
        run_nli=True,
    )

    # 4. Print results
    print("\n=== RETRIEVAL RESULTS ===\n")

    for claim, score, label, confidence in results:
        print("DEBUG CLAIM:", claim)
        print(
            f"Claim ID: {claim['id']}\n"
            f"Text: {claim['decontextualised_claim']}\n"
            f"Similarity: {score:.4f}\n"
            f"NLI: {label} ({confidence:.2f})\n"
            "------------------------"
        )


if __name__ == "__main__":
    main()
