import uuid
from sqlalchemy.orm import Session
from microservices.api.app.models.job import Job
from microservices.api.app.dtos.job import JobCreate, JobResponse, JobStatus, JobType
from microservices.api.app.core.logger import logger

def create_job(db: Session, job_in: JobCreate, article_id: int)->Job:
    uid:str = str(uuid.uuid4())
    logger.info(article_id)
    
    db_obj = Job(
        uid = uid,
        article_id = article_id,
        type = JobType.USER.value,
        status = JobStatus.PENDING.value
    )


    db.add(db_obj)
    db.flush()
    db.refresh(db_obj)
    logger.info(f"Prepared job for creation: {db_obj}")
    return db_obj


def get_job(db: Session, job_id: str):
    return db.query(Job).filter(Job.id == job_id).first()


def generate_db_statistics(db: Session):
    pass
