from fastapi import APIRouter, Depends, HTTPException
from microservices.api.app.db.session import get_db
from sqlalchemy.orm import Session


router = APIRouter()

# @router.post("/", response_model=JobResponse)
# def write_result(job_in: JobCreate, db: Session = Depends(get_db)):
# 	pass

# @router.get("/{result_id}", response_model=JobResponse)
# def read_result(result_id: str, db: Session = Depends(get_db)):
# 	pass

# @router.get("/statistics", response_model=JobResponse)
# def read_db_summary(db: Session = Depends(get_db)):
# 	pass
