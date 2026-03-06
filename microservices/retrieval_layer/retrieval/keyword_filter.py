from sqlalchemy.orm import Session
from sqlalchemy import or_, select
from microservices.retrieval_layer.db.models import Claim

def find_evidence_by_keyword_match(
    db: Session,
    keywords_to_match: list[str],
    limit: int = 50,
):
    if not keywords_to_match:
        return []

    conditions = [
        Claim.decontextualised_claim.ilike(f"%{kw}%")
        for kw in keywords_to_match
    ]

    stmt = select(Claim).where(or_(*conditions)).limit(limit)
    return db.execute(stmt).scalars().all()
