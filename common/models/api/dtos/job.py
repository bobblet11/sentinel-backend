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
    PRIORITISED = "prioritised"
    FETCHED_IN = "starting fetch HTML"
    FETCHED_OUT = "ending fetch HTML"
    PARSED_IN = "starting parsing HTML"
    PARSED_OUT = "ending parsing HTML"
    NLP_START = "started NLP"
    NLP_END = "completed NLP"
    IN = "in"
    OUT = "out"
    
class JobCreate(BaseModel):
    article_url: str
    article_html: str
class JobResponse(BaseModel):
    id: int
    status: str
    type: str
    created_at: datetime
