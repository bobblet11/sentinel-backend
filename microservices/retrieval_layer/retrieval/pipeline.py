from sqlalchemy.orm import Session
from microservices.retrieval_layer.retrieval.entity_filter import filter_by_entities
from microservices.retrieval_layer.retrieval.keyword_filter import filter_by_keywords
from microservices.retrieval_layer.retrieval.embedding_ranker import rank_by_embedding_similarity
from microservices.retrieval_layer.retrieval.nli import classify_claim_relation

def retrieve_candidate_claims(
    db: Session,
    claim_text: str,
    claim_embedding: list[float],
    entities: list[str],
    top_k: int = 5,
    run_nli: bool = True
):
    """
    Returns top-K candidate claims ranked by embedding similarity.
    Optionally runs NLI to classify support/contradict/irrelevant.
    """

    candidates = {}

    # 1. Entity filter
    for c in filter_by_entities(db, entities):
        candidates[c.id] = c

    # 2. Keyword filter
    keywords = claim_text.split()
    for c in filter_by_keywords(db, keywords):
        candidates[c.id] = c

    candidate_list = list(candidates.values())

    # 3. Embedding similarity ranking
    ranked = rank_by_embedding_similarity(
        user_embedding=claim_embedding,
        candidate_claims=candidate_list,
        top_k=top_k
    )

    # 4. NLI classification
    if run_nli:
        ranked_with_nli = []
        for claim, score in ranked:
            label, confidence = classify_claim_relation(claim_text, claim.decontextualised_claim)
            ranked_with_nli.append((claim, score, label, confidence))
        return ranked_with_nli

    return ranked  # list of (Claim, score)
