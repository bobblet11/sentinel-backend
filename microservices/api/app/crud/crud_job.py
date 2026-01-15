from sqlalchemy.orm import Session
from microservices.api.app.models.job import JobRequest
from microservices.api.app.dtos.job import JobCreate

def create_job(db: Session, job: JobCreate):
    db_obj = JobRequest(
        user_id=job.user_id,
        input_payload=job.input_payload,
        status="PENDING"
    )
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj

def get_job(db: Session, job_id: str):
    return db.query(JobRequest).filter(JobRequest.id == job_id).first()

def generate_db_statistics(db: Session):
    pass
