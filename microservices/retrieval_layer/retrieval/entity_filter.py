from sqlalchemy.orm import Session
from sqlalchemy import select
from microservices.retrieval_layer.db.models import Claim, Entity

def filter_by_entities(
    db: Session,
    entity_names: list[str],
    limit: int = 50,
):
    """
    Return claims that share at least one entity.
    """
    if not entity_names:
        return []

    stmt = (
        select(Claim)
        .join(Claim.entities)
        .where(Entity.name.in_(entity_names))
        .limit(limit)
    )

    return db.execute(stmt).scalars().all()
