from microservices.api_gateway.models.jobs import Job, JobStatus
from datetime import datetime
from typing import Dict
import uuid

_JOB_STORE: Dict[str, Job] = {}


class JobService:
    def create_job(self) -> Job:
        job_id = str(uuid.uuid4())
        job = Job(
            job_id=job_id,
            status=JobStatus.PENDING,
            created_at=datetime.utcnow()
        )
        _JOB_STORE[job_id] = job
        return job

    def get_job(self, job_id: str) -> Job | None:
        return _JOB_STORE.get(job_id)

    def complete_job(self, job_id: str, result: dict):
        job = _JOB_STORE[job_id]
        job.status = JobStatus.COMPLETED
        job.result = result
