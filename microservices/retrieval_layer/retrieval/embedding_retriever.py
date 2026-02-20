from sqlalchemy.orm import Session
from sqlalchemy import text
# from microservices.retrieval_layer.retrieval.embedding_utils import is_valid_embedding

MAX_CANDIDATES = 50  # hard cap BEFORE NLI


def is_valid_embedding(embedding, dim=768) -> bool:
    if embedding is None:
        return False
    if not isinstance(embedding, (list, tuple)):
        return False
    if len(embedding) != dim:
        return False
    return True

def retrieve_by_embedding(
    db: Session,
    query_embedding: list[float],
    candidate_claim_ids: list[int] | None = None,
    top_k: int = MAX_CANDIDATES,
    exclude_claim_id: int | None = None,
):
    if not is_valid_embedding(query_embedding):
        return []

    sql = """
    SELECT id, decontextualised_claim, decontextualised_embedding <=> CAST(:query_embedding AS vector) AS distance
    FROM claim
    WHERE decontextualised_embedding IS NOT NULL
    """


    if exclude_claim_id is not None:
        sql += " AND id != :exclude_id"

    sql += """
    ORDER BY decontextualised_embedding <=> CAST(:query_embedding AS vector)
    LIMIT :limit
    """

    params = {
        "query_embedding": query_embedding,
        "limit": top_k,
    }

        
    
    if exclude_claim_id is not None:
        params["exclude_id"] = exclude_claim_id

    rows = db.execute(text(sql), params).fetchall()
    
    if not rows:
        return []
    
    results = []
    for r in rows:
        similarity = 1 - r.distance  # cosine similarity

        claim = {
            "id": r.id,
            "decontextualised_claim": r.decontextualised_claim,
        }
        results.append(
            (claim, similarity)
        )

    return results
