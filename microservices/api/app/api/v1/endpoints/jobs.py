from fastapi import APIRouter, Depends, HTTPException
from microservices.api.app.db.session import get_db
from microservices.api.app.dtos.job import JobCreate, JobResponse
from microservices.api.app.crud import crud_job
from microservices.api.app.services import redis_queue
from sqlalchemy.orm import Session

router = APIRouter()

@router.post("/", response_model=JobResponse)
def submit_job(job_in: JobCreate, db: Session = Depends(get_db)):
	pass

@router.get("/{job_id}", response_model=JobResponse)
def read_job_status(job_id: str, db: Session = Depends(get_db)):
	pass
