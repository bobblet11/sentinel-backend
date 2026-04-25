from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from microservices.retrieval_layer.db.models import Article, Claim
from microservices.retrieval_layer.retrieval.common_words import STOP_WORDS


def extract_keywords(text: str) -> list[str]:
    words = [w.strip(" .,;:'\"").lower() for w in text.split()]
    return [w for w in words if w not in STOP_WORDS and len(w) > 2]


def find_evidence_by_keyword_match(
    db: Session,
    claim_text: str,
    limit: int = 50,
    exclude_article_id: int | None = None,
    published_after: datetime | None = None,
    published_before: datetime | None = None,
):
    """
    Match keywords against ARTICLE TITLES (better than claim text).
    """
    if not claim_text:
        return []

    keywords = extract_keywords(claim_text)

    if not keywords:
        return []

    stmt = select(Claim).join(Article, Article.id == Claim.article_id)

    if exclude_article_id is not None:
        stmt = stmt.where(Claim.article_id != exclude_article_id)

    title_filters = [Article.title.ilike(f"%{kw}%") for kw in keywords]

    stmt = (
        stmt.where(Article.title.is_not(None)).where(or_(*title_filters)).limit(limit)
    )

    if published_after:
        stmt = stmt.where(Article.publishedAt >= published_after)
    if published_before:
        stmt = stmt.where(Article.publishedAt <= published_before)

    return db.execute(stmt).scalars().all()


# 🔥 IMPORTANT: keep this so pipeline.py DOES NOT BREAK
find_evidence_by_tfidf = find_evidence_by_keyword_match
