from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from microservices.retrieval_layer.db.models import Article, Claim, Entity


def find_evidence_by_entity_match(
    db: Session,
    entity_names_to_match: list[str],
    limit: int = 50,
    exclude_article_id: int | None = None,
    published_after: datetime | None = None,
    published_before: datetime | None = None,

):
    """
    Return claims that share at least one entity.
    """
    if not entity_names_to_match:
        return []
    
    # this query can be improved. match type and Name, change later
    stmt = (
        select(Claim)
        .join(Claim.entities)
        .join(Article, Article.id == Claim.article_id)
        .where(Entity.name.in_(entity_names_to_match))
    )

    if exclude_article_id is not None:
        stmt = stmt.where(Claim.article_id != exclude_article_id)
        
    if published_after:
        stmt = stmt.where(Article.publishedAt >= published_after)
    if published_before:
        stmt = stmt.where(Article.publishedAt <= published_before)

    stmt = stmt.limit(limit)

    return db.execute(stmt).scalars().all()
