from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from microservices.api_gateway.services.job_service import JobService
from microservices.api_gateway.services.queue_service import QueueService
# microservices/api_gateway/routers/analysis.py
import logging
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

logger = logging.getLogger("api_gateway.analysis")

router = APIRouter(prefix="/analysis", tags=["analysis"])

job_service = JobService()
queue_service = QueueService()


class AnalyzeRequest(BaseModel):
    title: str
    url: str
    content: str
    


@router.post("/analyze")
def analyze_article(req: AnalyzeRequest):
    job = job_service.create_job()

    queue_service.publish_analysis_job(
        job_id=job.job_id,
        url=req.url,
        content=req.content,
        title=req.title
    )

    return {
        "job_id": job.job_id,
        "status": job.status
    }


@router.get("/jobs/{job_id}")
def get_job(job_id: str):
    job = job_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status != "COMPLETED":
        return {
            "job_id": job.job_id,
            "status": job.status
        }

    return job.result
