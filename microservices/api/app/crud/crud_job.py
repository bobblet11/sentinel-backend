import uuid

from sqlalchemy.orm import Session

from microservices.api.app.core.logger import logger
from microservices.api.app.dtos.job import JobCreate, JobStatus, JobType
from microservices.api.app.models.job import Job


def create_job(db: Session, job_in: JobCreate, article_id: int)->Job:
    uid:str = str(uuid.uuid4())
    logger.info(article_id)
    
    db_obj = Job(
        uid = uid,
        article_id = article_id,
        type = JobType.USER.value if not job_in.is_background else JobType.BACKGROUND.value,
        status = JobStatus.PENDING.value 
    )


    db.add(db_obj)
    db.flush()
    db.refresh(db_obj)
    logger.info(f"Prepared job for creation: {db_obj}")
    return db_obj


def get_job(db: Session, job_id: int):
    return db.query(Job).filter(Job.id == job_id).first()


def get_latest_job_for_article(db: Session, article_id: int, job_type: str) -> Job | None:
    return (
        db.query(Job)
        .filter(Job.article_id == article_id, Job.type == job_type)
        .order_by(Job.created_at.desc(), Job.id.desc())
        .first()
    )


def generate_db_statistics(db: Session):
    pass
