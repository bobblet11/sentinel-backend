from fastapi import APIRouter, Depends, HTTPException, status, Query
from psycopg2 import IntegrityError
from microservices.api.app.crud.crud_article import create_article
from microservices.api.app.db.session import get_db
from microservices.api.app.dtos.job import JobCreate, JobResponse
from microservices.api.app.crud.crud_job import create_job, get_job
from microservices.api.app.models.article import Article
from microservices.api.app.models.job import Job
from microservices.api.app.services.redis_queue import publish_job
from sqlalchemy.orm import Session
from uuid import UUID
import asyncio
import json
from common.redis_client.connection import RedisConnection

router = APIRouter()
redis_connection = RedisConnection()

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


@router.get("/{job_uid}/result", response_model=dict, status_code=status.HTTP_200_OK)
async def get_retrieval_result(job_uid: UUID, timeout: int = Query(30, ge=5, le=60), db: Session = Depends(get_db)):
    """
    Poll Redis for retrieval results matching the job_uid.
    
    Extension calls this endpoint every 5s until it gets a result.
    - Returns 200 with formatted result when retrieval completes
    - Returns 404 if result not found after timeout
    """
    try:
        client = redis_connection.get_client()
        start_time = asyncio.get_event_loop().time()
        search_for_uid = str(job_uid)
        
        while asyncio.get_event_loop().time() - start_time < timeout:
            # Read all messages from retrieval results stream (from beginning to latest)
            # xrange(key, min, max) with min='-' (earliest) and max='+' (latest)
            results = client.xrange("user:retrieval.results", min="-", max="+", count=100)
            
            # redis_connection uses decode_responses=True, so all data is already strings
            for msg_id, data in results:
                if 'payload' in data:
                    try:
                        # data['payload'] is already a string (not bytes)
                        payload = json.loads(data['payload'])
                        found_uid = str(payload.get('job_uid', ''))
                        
                        if found_uid == search_for_uid:
                            retrieval_result = payload.get('retrieval_result', {})
                            return {
                                "ok": True,
                                "job_uid": str(job_uid),
                                "status": payload.get('status', 'completed'),
                                "data": retrieval_result
                            }
                    except (json.JSONDecodeError, TypeError) as e:
                        continue
            
            await asyncio.sleep(1)
        
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Retrieval result not found for job {job_uid} within {timeout}s"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving result: {str(e)}"
        )
