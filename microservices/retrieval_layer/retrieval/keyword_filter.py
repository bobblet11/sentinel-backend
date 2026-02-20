from sqlalchemy.orm import Session
from sqlalchemy import select
from microservices.retrieval_layer.db.models import Claim

def filter_by_keywords(
    db: Session,
    keywords: list[str],
    limit: int = 50,
):
    if not keywords:
        return []

    conditions = [
        Claim.decontextualised_claim.ilike(f"%{kw}%")
        for kw in keywords
    ]

    stmt = select(Claim).where(*conditions).limit(limit)
    return db.execute(stmt).scalars().all()
