from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from microservices.api.app.db.session import get_db
from microservices.api.app.models.article import Article, NewsOutlet, SentimentAnalysis

router = APIRouter()
outlets_router = APIRouter()


def _article_to_dict(article: Article) -> Dict[str, Any]:
    sentiment = article.sentiment
    return {
        "id": str(article.id),
        "title": article.title or "Untitled",
        "article_url": article.url or "",
        "news_outlet": article.outlet.name if article.outlet else "Unknown",
        "bias": sentiment.bias_category if sentiment else "Unknown",
        "trust_score": round((sentiment.bias_analysis_confidence or 0) * 100) if sentiment else 0,
        "created_at": article.publishedAt.isoformat() if article.publishedAt else None,
    }


def _base_query(db: Session):
    return (
        db.query(Article)
        .outerjoin(NewsOutlet, Article.outlet_id == NewsOutlet.id)
        .outerjoin(SentimentAnalysis, Article.sentiment_id == SentimentAnalysis.id)
    )


@router.get("")
def get_articles(
    search: Optional[str] = None,
    leaning: Optional[str] = None,
    outlet: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    query = _base_query(db)

    if search:
        pattern = f"%{search}%"
        query = query.filter(
            or_(
                Article.title.ilike(pattern),
                NewsOutlet.name.ilike(pattern),
            )
        )
    if leaning:
        query = query.filter(
            func.lower(SentimentAnalysis.bias_category) == leaning.lower()
        )
    if outlet:
        query = query.filter(NewsOutlet.name == outlet)
    if date_from:
        query = query.filter(Article.publishedAt >= date_from)
    if date_to:
        query = query.filter(Article.publishedAt <= date_to)

    total = query.count()
    rows = (
        query.order_by(Article.publishedAt.desc().nulls_last())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )

    return {
        "articles": [_article_to_dict(row) for row in rows],
        "total": total,
        "page": page,
        "pages": (total + limit - 1) // limit,
    }


@outlets_router.get("")
def get_outlets(db: Session = Depends(get_db)) -> List[str]:
    rows = db.query(NewsOutlet.name).distinct().order_by(NewsOutlet.name).all()
    return [r[0] for r in rows if r[0]]
