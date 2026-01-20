from sqlalchemy.orm import Session
from microservices.api.app.models.article import Article
from microservices.api.app.models.job import Job
from microservices.api.app.dtos.job import JobCreate 
from microservices.api.app.core.logger import logger

def create_article(db: Session, job_in: JobCreate)->Article:
    db_obj = Article(
        url = job_in.article_url,
        html = job_in.article_html
    )

    db.add(db_obj)
    db.flush()
    db.refresh(db_obj)
    logger.info(f"Prepared article for creation: {db_obj}")
    return db_obj

