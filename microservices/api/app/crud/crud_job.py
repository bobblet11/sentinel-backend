from sqlalchemy.orm import Session
from microservices.api.app.models.job import Job
from microservices.api.app.dtos.job import JobCreate, JobResponse, JobStatus, JobType

def create_job(db: Session, job_dto: JobCreate)->JobResponse:
    try:
        db_obj = Job(
            type = JobType.USER,
            status = JobStatus.PENDING
        )
        # use job_dto to add article entry as well and link to job
        
    
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj
    except Exception as e:
        db.rollback()


def get_job(db: Session, job_id: str):
    return db.query(Job).filter(Job.id == job_id).first()


def generate_db_statistics(db: Session):
    pass
