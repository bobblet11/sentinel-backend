from sqlalchemy.orm import Session
from sqlalchemy import select
from microservices.retrieval_layer.models import (
    Article, Claim, Entity, NewsOutlet, Author, SentimentAnalysis, claim_to_entity_table
)
from datetime import datetime
from typing import Dict, Any, Optional


def get_or_create_outlet(db: Session, name: str, leaning: Optional[str] = None) -> NewsOutlet:
    row = db.execute(select(NewsOutlet).where(NewsOutlet.name == name)).scalar_one_or_none()
    if row:
        return row
    n = NewsOutlet(name=name, leaning=leaning)
    db.add(n)
    db.flush()
    return n


def get_or_create_author(db: Session, name: str) -> Author:
    row = db.execute(select(Author).where(Author.name == name)).scalar_one_or_none()
    if row:
        return row
    a = Author(name=name)
    db.add(a)
    db.flush()
    return a


def get_or_create_entity(db: Session, name: str, type_: Optional[str] = None) -> Entity:
    q = select(Entity).where(Entity.name == name)
    if type_:
        q = q.where(Entity.type == type_)
    row = db.execute(q).scalar_one_or_none()
    if row:
        return row
    e = Entity(name=name, type=type_)
    db.add(e)
    db.flush()
    return e


def get_or_create_sentiment(db: Session, sent: Dict[str, Any]) -> SentimentAnalysis:
    
    s = SentimentAnalysis(
        bias_category=sent.get("bias_category"),
        bias_score=sent.get("bias_score"),
        bias_analysis_confidence=sent.get("bias_analysis_confidence"),
        sentiment_category=sent.get("sentiment_category"),
        sentiment_analysis_confidence=sent.get("sentiment_analysis_confidence"),
    )
    db.add(s)
    db.flush()
    return s


def get_or_create_article(db: Session, article_d: Dict[str, Any]) -> Article:
    url = article_d.get("url")
    if not url:
        raise ValueError("article must include url")

    row = db.execute(select(Article).where(Article.url == url)).scalar_one_or_none()
    if row:
        return row

    outlet_name = article_d.get("outlet_name") or article_d.get("source") or article_d.get("news_outlet")
    outlet = None
    if outlet_name:
        outlet = get_or_create_outlet(db, outlet_name)

    sentiment = None
    if article_d.get("sentiment"):
        sentiment = get_or_create_sentiment(db, article_d["sentiment"])

    published_at = None
    if article_d.get("publishedAt"):
        try:
            published_at = datetime.fromisoformat(article_d["publishedAt"])
        except Exception:
            published_at = None

    article = Article(
        url=url,
        title=article_d.get("title"),
        text=article_d.get("text") or article_d.get("content"),
        html=article_d.get("html"),
        publishedAt=published_at,
        outlet=outlet,
        sentiment_id=sentiment.id if sentiment else None,
    )
    db.add(article)
    db.flush()

    return article


def create_claim_and_link_entities(
    db: Session,
    claim_d: Dict[str, Any],
    article_obj: Article,
) -> Claim:
    """
    claim_d expected keys:
      - original_sentence
      - decontextualised_claim
      - decontextualised_embedding (list or None)
      - centrality_score (float)
      - entities: list of {'name','type'}
    """
    claim = Claim(
        original_sentence=claim_d.get("original_sentence"),
        decontextualised_claim=claim_d.get("decontextualised_claim"),
        decontextualised_embedding=claim_d.get("decontextualised_embedding"),
        centrality_score=claim_d.get("centrality_score"),
        article_id=article_obj.id,
    )
    db.add(claim)
    db.flush()

    entities = claim_d.get("entities", []) or []
    for ent in entities:
        name = ent.get("name")
        type_ = ent.get("type")
        if not name:
            continue
        db_ent = get_or_create_entity(db, name=name, type_=type_)
        if db_ent not in claim.entities:
            claim.entities.append(db_ent)
    db.flush()
    return claim
