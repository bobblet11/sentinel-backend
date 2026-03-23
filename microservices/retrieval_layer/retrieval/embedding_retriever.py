from typing import Dict, List, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import select, text
from microservices.retrieval_layer.db.models import Article, Claim
from pgvector.sqlalchemy import Vector
MAX_CANDIDATES = 100  # hard cap BEFORE NLI


def is_valid_embedding(embedding, dim=768) -> bool:
    if embedding is None:
        return False
    if not isinstance(embedding, (list, tuple)):
        return False
    if len(embedding) != dim:
        return False
    return True


#top k is not good, replace it with teh thing we learned in NLP, convert every candidate into a percentage, sum up all the claims until it reaches some  threshold.
def retrieve_by_embedding(
    db: Session,
    query_embedding: list[float],
    candidate_claim_ids: list[int],  
    top_k: int = MAX_CANDIDATES,
    exclude_claim_id: int | None = None,
    exclude_article_id: int | None = None,
) -> List[Tuple[Dict[str, str | int], float]]:
    
    if not is_valid_embedding(query_embedding):
        return []
    
    if not candidate_claim_ids:
        return []

    
    query_vec = query_embedding
    distance_expr = Claim.decontextualised_embedding.cosine_distance(query_vec)
    stmt = (
        select(
            Claim.id,
            Claim.decontextualised_claim,
            Claim.article_id,
            Article.url,
            Article.text,
            distance_expr.label("distance"),
        )
        .join(Article, Article.id == Claim.article_id)
        .where(Claim.decontextualised_embedding.is_not(None))
        .where(Claim.id.in_(candidate_claim_ids))
        .order_by(distance_expr)
    )
        
    if exclude_claim_id:
        stmt = stmt.where(Claim.id != exclude_claim_id)
    if exclude_article_id is not None:
        stmt = stmt.where(Claim.article_id != exclude_article_id)
    
    stmt = stmt.order_by(Claim.decontextualised_embedding.cosine_distance(query_vec)).limit(top_k)
    results = db.execute(stmt).fetchall()
    
    processed = []
    for row in results:
        similarity = 1.0 - row.distance
        raw_text = row.text or ""
        source_excerpt = raw_text[:300] + ("..." if len(raw_text) > 300 else "")
        claim_dict = {
            "id": row.id,
            "decontextualised_claim": row.decontextualised_claim,
            "article_id": row.article_id,
            "source_url": row.url,
            "source_excerpt": source_excerpt,
        }
        processed.append((claim_dict, similarity))
    
    return processed


def retrieve_by_embedding_full_scan(
    db: Session,
    query_embedding: list[float],
    top_k: int = MAX_CANDIDATES,
    exclude_claim_id: int | None = None,
) -> List[Tuple[Dict[str, str | int], float]]:
    if not is_valid_embedding(query_embedding):
        return []
    
    query_vec = Vector(query_embedding)
    stmt = (
        select(
            Claim.id,
            Claim.decontextualised_claim,
            Claim.decontextualised_embedding.cosine_distance(query_vec).label("distance")
        )
        .where(Claim.decontextualised_embedding.is_not(None))
    )
    
    if exclude_claim_id:
        stmt = stmt.where(Claim.id != exclude_claim_id)
    
    stmt = stmt.order_by(Claim.decontextualised_embedding.cosine_distance(query_vec)).limit(top_k)
    results = db.execute(stmt).fetchall()
    
    processed = []
    for row in results:
        similarity = 1.0 - row.distance
        claim_dict = {
            "id": row.id,
            "decontextualised_claim": row.decontextualised_claim,
        }
        processed.append((claim_dict, similarity))
    
    return processed
