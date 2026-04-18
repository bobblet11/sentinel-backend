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
    article_text: str | None = None
    article_title: str | None = None
    article_author: str | None = None
    article_published_at: str | None = None
    article_summary: str  | None = None
    
    news_outlet: str | None = None
    is_background: bool = False

class JobResponse(BaseModel):
    id: int
    uid: UUID
    status: str
    type: str
    created_at: datetime
