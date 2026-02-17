from microservices.retrieval_layer.db.session import get_db_session
from microservices.retrieval_layer.retrieval.pipeline import retrieve_candidate_claims

db = get_db_session()

user_embedding = [0.01,0.02,0.03,0.01,0.00,0.04,0.05,0.02] * 38  # 304-D

results = retrieve_candidate_claims(
    db,
    claim_text="Government increased taxes",
    claim_embedding=user_embedding,
    entities=["Government", "taxes"],
    top_k=3,
    run_nli=True
)

for claim, score, label, confidence in results:
    print(claim.id, claim.decontextualised_claim, f"{label} ({confidence:.2f})")
