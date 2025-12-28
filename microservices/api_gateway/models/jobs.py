from enum import Enum
from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class JobStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Job(BaseModel):
    job_id: str
    status: JobStatus
    created_at: datetime
    result: Optional[dict] = None
