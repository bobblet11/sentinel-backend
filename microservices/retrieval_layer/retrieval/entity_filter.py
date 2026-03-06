from sqlalchemy.orm import Session
from sqlalchemy import select
from microservices.retrieval_layer.db.models import Claim, Entity

def find_evidence_by_entity_match(
    db: Session,
    entity_names_to_match: list[str],
    limit: int = 50,
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
        .where(Entity.name.in_(entity_names_to_match))
        .limit(limit)
    )

    return db.execute(stmt).scalars().all()
