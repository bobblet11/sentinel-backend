from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from microservices.api.app.models.article import Article, NewsOutlet
from microservices.api.app.models.job import Job
from microservices.api.app.dtos.job import JobCreate 
from microservices.api.app.core.logger import logger


def get_or_create_outlet(db: Session, name: str) -> NewsOutlet:
    row = db.execute(select(NewsOutlet).where(NewsOutlet.name == name)).scalar_one_or_none()
    if row:
        return row
    outlet = NewsOutlet(name=name)
    db.add(outlet)
    db.flush()
    return outlet

def create_article(db: Session, job_in: JobCreate)->Article:
    outlet = None
    if job_in.news_outlet:
        outlet = get_or_create_outlet(db, job_in.news_outlet)

    db_obj = Article(
        url = job_in.article_url,
        title = job_in.article_title,
        html = job_in.article_html,
        text = job_in.article_text,
        outlet_id = outlet.id if outlet else None,
    )

    db.add(db_obj)
    db.flush()
    db.refresh(db_obj)
    logger.info(f"Prepared article for creation: {db_obj}")
    return db_obj

