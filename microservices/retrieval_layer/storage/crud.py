from dataclasses import asdict
from typing import Any, Dict, List

from sqlalchemy import select, text
from sqlalchemy.orm import Session, joinedload

from microservices.retrieval_layer.db.models import (Article, Author, Claim,
                                                     Entity, Job, JobTimestamp,
                                                     NewsOutlet,
                                                     SentimentAnalysis, Topic)
from microservices.retrieval_layer.storage.dtos import (
    CreateOrModifyArticle, CreateOrModifyClaim, CreateOrModifyOutlet,
    CreateOrModifySentiment, Evidence, UpdateJob, UpsertArticleTopic)


def get_or_create_author(db: Session, name: str) -> Author:
    row = db.execute(select(Author).where(Author.name == name)).scalar_one_or_none()
    if row:
        return row
    a = Author(name=name)
    db.add(a)
    db.flush()
    return a

#first entity is redis model, second entity is db obj
def get_or_create_all_entities(db: Session, entities: List[Entity]) -> List[Entity]:
    
    added_entities:List[Entity] = []
    existing_entities: List[Entity] = []
    for entity in entities:
        # name = entity.name
        # type_ = entity.type
        name = entity.entity_text
        type_ = entity.type_of_entity
        
        query_to_find_entity = select(Entity).where(Entity.name == name)
        if type_:
            query_to_find_entity = query_to_find_entity.where(Entity.type == type_)
            
        existing_entity = db.execute(query_to_find_entity).scalar_one_or_none()
        
        if existing_entity:
            existing_entities.append(existing_entity)
            continue
        
        new_entity = Entity(name=name, type=type_)
        db.add(new_entity)
        db.flush()
        db.refresh(new_entity)
        added_entities.append(new_entity)
    return added_entities + existing_entities

def create_sentiment(db: Session, sentiment_dto: CreateOrModifySentiment) -> SentimentAnalysis:
    new_sentiment_entry = SentimentAnalysis(
        bias_category=sentiment_dto.bias_category,
        bias_analysis_confidence=sentiment_dto.bias_analysis_confidence,
        sentiment_category=sentiment_dto.sentiment_category,
        sentiment_analysis_confidence=sentiment_dto.sentiment_analysis_confidence,
    )
    
    db.add(new_sentiment_entry)
    db.flush()
    return new_sentiment_entry

def get_or_create_outlet(db: Session, outlet_dto: CreateOrModifyOutlet) -> NewsOutlet:
    
    existing_outlet_entry = db.execute(select(NewsOutlet).where(NewsOutlet.name == outlet_dto.name)).scalar_one_or_none()
    if existing_outlet_entry:
        return existing_outlet_entry
    
    new_outlet_entry = NewsOutlet(name=outlet_dto.name)
    db.add(new_outlet_entry)
    db.flush()
    return new_outlet_entry
    
def get_or_create_article(db: Session, article_dto: CreateOrModifyArticle, sentiment_dto: CreateOrModifySentiment, outlet_dto: CreateOrModifyOutlet) -> Article:
    if not article_dto.article_url:
        raise ValueError("article must include url")

    stmt = select(Article).where(Article.url == article_dto.article_url)
    existing = db.execute(stmt).scalar_one_or_none()
    
    outlet_entry = None
    if outlet_dto.name:
        outlet_entry = get_or_create_outlet(db, outlet_dto)
        
    sentiment_entry = create_sentiment(db, sentiment_dto)
    
    author_entry = None
    if article_dto.author:
        author_entry = get_or_create_author(db, article_dto.author)
    
    
    if existing:
        # Always overwrite all fields, even if they were already set
        existing.html = article_dto.article_html
        existing.text = article_dto.article_text
        existing.title = article_dto.article_title
        existing.publishedAt = article_dto.publish_date

        existing.outlet_id = outlet_entry.id if outlet_entry else None
        existing.sentiment_id = sentiment_entry.id if sentiment_entry else None
        existing.author_id = author_entry.id if author_entry else None  # ADD

        db.flush()
        return existing
    
    new_article_entry = Article(
        url=article_dto.article_url,
        title=article_dto.article_title,
        text=article_dto.article_text,
        html=article_dto.article_html,
        publishedAt=article_dto.publish_date,
        outlet_id=outlet_entry.id if outlet_entry else None,
        sentiment_id=sentiment_entry.id if sentiment_entry else None,
        author_id=author_entry.id if author_entry else None,  # ADD

    )
    
    db.add(new_article_entry)
    db.flush()
    return new_article_entry

def create_claim_and_link_entities(
    db: Session,
    claim_dto: CreateOrModifyClaim,
    article_entry: Article,
) -> Claim:
    
    claim = Claim(
        original_sentence=claim_dto.original_sentence,
        decontextualised_claim=claim_dto.decontextualised_claim,
        decontextualised_embedding=claim_dto.decontextualised_embedding,
        centrality_score=claim_dto.centrality_score,
        article_id=article_entry.id
    )
    
    db.add(claim)
    db.flush()
    db.refresh(claim)
#added parts
    entities = get_or_create_all_entities(db, claim_dto.NER_entities)
    claim.entities.extend(entities)
    db.flush()
    return claim

def extend_evidence_claims_into_articles(db: Session, claim_ids: List[int], current_article_id: int) -> List[Dict[str, Any]]:
    """
    Fetch related articles based on matched claim IDs.
    Returns articles that contain the matched claims, excluding the current article.
    """
    
    if not claim_ids:
        return []
    
    articles = db.execute(
        select(Article)
        .options(joinedload(Article.outlet))
        .options(joinedload(Article.sentiment))
        .join(Claim, Claim.article_id == Article.id)
        .where(Claim.id.in_(claim_ids))
        .where(Article.id != current_article_id)
        .distinct(Article.id)
    ).scalars().unique().all()
    
    if not articles:
        return []
    
    related = []
    for article in articles:
    
        article_excerpt = article.text[:300] if article.text else ""
        if len(article.text or "") > 300:
            article_excerpt += "..."
        
        bias_category = article.sentiment.bias_category if article.sentiment and article.sentiment.bias_category  else "center"
        
        if bias_category.lower() not in ["left", "center-left", "center", "center-right", "right"]:
            mapping = {
                "liberal": "left",
                "progressive": "left",
                "conservative": "right",
                "neutral": "center",
                "moderate": "center",
            }
            bias_category = mapping.get(bias_category.lower() , "center")

        
        evidence = Evidence(
            id = str(article.id),
            title = article.title or "Untitled",
            source = article.outlet.name if article.outlet else "Unknown",
            url = article.url,
            bias = bias_category,
            publishedAt = article.publishedAt.isoformat() if article.publishedAt else "",
            excerpt = article_excerpt
        )
        
        # Hash store serialization expects JSON-serializable values.
        related.append(asdict(evidence))
    return related


def upsert_article_topic(db: Session, dto: UpsertArticleTopic) -> None:
    topic_row = db.execute(
        select(Topic).where(Topic.name == dto.topic_label)
    ).scalar_one_or_none()
    if topic_row is None:
        return
    db.execute(
        text(
            """
            INSERT INTO article_topic (article_id, topic_id, confidence)
            VALUES (:article_id, :topic_id, :confidence)
            ON CONFLICT (article_id)
            DO UPDATE SET topic_id   = EXCLUDED.topic_id,
                          confidence = EXCLUDED.confidence
            """
        ),
        {
            "article_id": dto.article_id,
            "topic_id": topic_row.id,
            "confidence": dto.topic_confidence,
        },
    )
    db.flush()


def finalise_and_complete_job(db: Session, job_dto: UpdateJob):
    if not job_dto.job_id or not job_dto.job_uid:
        raise ValueError("job must include id and uid")
    
    query_to_find_job = select(Job).where(Job.id == job_dto.job_id, Job.uid == job_dto.job_uid)
    existing_job = db.execute(query_to_find_job).scalar_one_or_none()

    if not existing_job:
        raise ValueError("job does not exist! should exist for user jobs")

    # Persist status transition (e.g. pending -> complete) once retrieval finalizes.
    existing_job.status = str(job_dto.status)

    # Idempotency guard: skip stages that are already present for this job.
    existing_stage_names = set(
        db.execute(
            select(JobTimestamp.stage_name).where(JobTimestamp.job_id == existing_job.id)
        ).scalars().all()
    )

    for timestamp in job_dto.stage_timestamps:
        if timestamp.stage_name in existing_stage_names:
            continue

        jt_to_add = JobTimestamp(
            job_id=existing_job.id,
            stage_name=timestamp.stage_name,
            timestamp=timestamp.wall_time,
            # monotonic_timestamp = timestamp.offset_s
        )
        db.add(jt_to_add)
        
    db.flush()
    return existing_job
