from sqlalchemy.orm import Session
from microservices.retrieval_layer.retrieval.entity_filter import filter_by_entities
from microservices.retrieval_layer.retrieval.keyword_filter import filter_by_keywords
from microservices.retrieval_layer.retrieval.embedding_retriever import retrieve_by_embedding
from microservices.retrieval_layer.retrieval.nli import classify_claim_relation

MAX_CANDIDATES_BEFORE_EMBEDDING = 100
MAX_CANDIDATES_BEFORE_NLI = 10
MIN_SIMILARITY = 0.25


def retrieve_candidate_claims(
    db: Session,
    claim_text: str,
    claim_embedding: list[float],
    entities: list[str],
    top_k: int = 5,
    run_nli: bool = True,
    exclude_claim_id: int | None = None,
):
    """
    Returns top-K candidate claims ranked by embedding similarity.
    Optionally runs NLI to classify support/contradict/irrelevant.
    """

    # ---------- Embedding validation ----------
    if not claim_embedding or not isinstance(claim_embedding, list):
        raise ValueError("claim_embedding must be a non-empty list")

    # ---------- 1. Symbolic filtering ----------
    candidates = {}

    for c in filter_by_entities(db, entities):
        candidates[c.id] = c

    keywords = claim_text.split()
    for c in filter_by_keywords(db, keywords):
        candidates[c.id] = c

    candidate_list = list(candidates.values())
    
    # print("Entities:", entities)
    # print("Keywords:", keywords)
    # print("Candidates after symbolic:", len(candidate_list))

    if not candidate_list:
        return []

    # Hard cap before embedding search
    candidate_list = candidate_list[:MAX_CANDIDATES_BEFORE_EMBEDDING]

    # ---------- 2. Embedding similarity (pgvector) ----------
    ranked = retrieve_by_embedding(
        db=db,
        query_embedding=claim_embedding,
        candidate_claim_ids=[c.id for c in candidate_list],
        top_k=top_k,
        exclude_claim_id=exclude_claim_id,
    )
    # ranked = list[(Claim, similarity)]

    # Similarity threshold
    ranked = [(c, s) for c, s in ranked if s >= MIN_SIMILARITY]

    if not ranked:
        return []

    # Cap before NLI
    ranked = ranked[:MAX_CANDIDATES_BEFORE_NLI]
    
    # print("Ranked after embedding:", ranked)
    # for c, s in ranked:
    #     print(type(c), c)

    # ---------- 3. NLI ----------
    if not run_nli:
        return ranked

    ranked_with_nli = []

    for claim, score in ranked:
        try:
            label, confidence = classify_claim_relation(
                claim_text,
                claim["decontextualised_claim"]
            )
        except Exception as e:
            print(f"Error during NLI for claim ID {claim['id']}:")
            print(e)
            label, confidence = "irrelevant", 0.0

        ranked_with_nli.append(
            (claim, score, label, confidence)
        )

    return ranked_with_nli
