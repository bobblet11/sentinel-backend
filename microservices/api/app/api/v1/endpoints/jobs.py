from fastapi import APIRouter, Depends, HTTPException, status
from psycopg2 import IntegrityError
from microservices.api.app.crud.crud_article import create_article
from microservices.api.app.db.session import get_db
from microservices.api.app.dtos.job import JobCreate, JobResponse
from microservices.api.app.crud.crud_job import create_job, get_job
from microservices.api.app.models.article import Article
from microservices.api.app.models.job import Job
from microservices.api.app.services.redis_queue import publish_job
from sqlalchemy.orm import Session
router = APIRouter()

# Accept both /jobs and /jobs/ to avoid 307 redirects
@router.post("", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
@router.post("/", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
def submit_job(job_in: JobCreate, db: Session = Depends(get_db)):
    try:
        # Start of the "Unit of Work"
        new_article: Article = create_article(db=db, job_in=job_in)
        new_job: Job = create_job(db=db, job_in=job_in, article_id=new_article.id)
        
        # Only publish to Redis if the database commit was successful.
        publish_job(new_job, new_article, job_in)
        
        # All database operations are prepared. Now, commit them as one transaction.
        db.commit() 
        return new_job

    except IntegrityError as e:
        # This can happen if, for example, the article URL already exists (violating a UNIQUE constraint)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Resource already exists. Error: {e.orig}"
        )
    except Exception as e:
        # For any other unexpected error, rollback the entire transaction
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {e}"
        )


@router.get("/{job_id}", response_model=JobResponse, status_code=status.HTTP_200_OK)
def read_job_status(job_id: int, db: Session = Depends(get_db)):
    job = get_job(db=db, job_id=job_id)

    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job with ID {job_id} not found."
        )
    
    return job
