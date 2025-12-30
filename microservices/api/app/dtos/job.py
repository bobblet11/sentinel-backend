from pydantic import BaseModel
from typing import Optional, Dict, Any
from uuid import UUID
from datetime import datetime

# What the user sends to create a job
class JobCreate(BaseModel):
    user_id: str
    input_payload: Dict[str, Any]

# What the API returns to the user
class JobResponse(BaseModel):
    id: UUID
    status: str
    result_data: Optional[Dict[str, Any]] = None
    created_at: datetime

    class Config:
        orm_mode = True # Allows Pydantic to read SQLAlchemy objects
