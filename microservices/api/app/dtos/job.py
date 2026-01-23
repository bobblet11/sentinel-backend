from pydantic import BaseModel
from typing import Optional, Dict, Any
from uuid import UUID
from datetime import datetime
from enum import StrEnum
class JobStatus(StrEnum):
    PENDING = "pending"
    COMPLETE = "complete"
    FAILED = "failed"
    
class JobType(StrEnum):
    BACKGROUND = "background"
    USER = "user"
    
class JobStage(StrEnum):
    INGESTED = "ingested"
    FETCHED = "fetched HTML"
    PARSED = "parsed HTML"
    NLP_START = "started NLP"
    NLP_END = "completed NLP"
    
class JobCreate(BaseModel):
    article_url: str
    article_html: str | None = None
    
    title: str | None = None
    news_outlet: str | None = None
    summary: str  | None = None
    
    is_background: bool = False

class JobResponse(BaseModel):
    id: int
    status: str
    type: str
    created_at: datetime
