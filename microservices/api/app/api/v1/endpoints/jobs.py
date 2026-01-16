from fastapi import APIRouter, Depends, HTTPException, status
from microservices.api.app.db.session import get_db
from microservices.api.app.dtos.job import JobCreate, JobResponse
from microservices.api.app.crud.crud_job import create_job, get_job
from microservices.api.app.services import redis_queue
from sqlalchemy.orm import Session

router = APIRouter()

@router.post("/", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
def submit_job(job_in: JobCreate, db: Session = Depends(get_db)):
        new_job: JobResponse = create_job(db=db, job_in=job_in)
        
        # redis_queue.enqueue_job(job_id=new_job.id, article_url=new_job.article_url)
        
        return new_job


@router.get("/{job_id}", response_model=JobResponse, status_code=status.HTTP_200_OK)
def read_job_status(job_id: str, db: Session = Depends(get_db)):
    job = get_job(db=db, job_id=job_id)

    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job with ID {job_id} not found."
        )
    
    return job
