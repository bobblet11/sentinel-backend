import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from microservices.api.app.db.session import get_db
from microservices.api.app.models.article import Article, ArticleTopic, Topic

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("", response_model=List[Dict[str, Any]])
def list_topics(db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    """List all topics with the number of articles assigned to each."""
    rows = db.execute(
        select(Topic.name, func.count(ArticleTopic.id).label("article_count"))
        .outerjoin(ArticleTopic, ArticleTopic.topic_id == Topic.id)
        .group_by(Topic.id, Topic.name)
        .order_by(Topic.name)
    ).all()

    return [{"topic": row.name, "article_count": row.article_count} for row in rows]


@router.get("/{topic_name}/articles", response_model=List[Dict[str, Any]])
def list_articles_by_topic(
    topic_name: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """List articles assigned to a given topic, paginated."""
    topic_row = db.execute(
        select(Topic).where(func.lower(Topic.name) == topic_name.lower())
    ).scalar_one_or_none()

    if topic_row is None:
        raise HTTPException(status_code=404, detail=f"Topic '{topic_name}' not found")

    offset = (page - 1) * page_size

    rows = db.execute(
        select(
            Article.id,
            Article.title,
            Article.url,
            Article.publishedAt,
            ArticleTopic.confidence,
        )
        .join(ArticleTopic, ArticleTopic.article_id == Article.id)
        .where(ArticleTopic.topic_id == topic_row.id)
        .order_by(ArticleTopic.confidence.desc(), Article.id.desc())
        .offset(offset)
        .limit(page_size)
    ).all()

    return [
        {
            "id": row.id,
            "title": row.title,
            "url": row.url,
            "publishedAt": row.publishedAt.isoformat() if row.publishedAt else None,
            "confidence": round(row.confidence, 4),
        }
        for row in rows
    ]
