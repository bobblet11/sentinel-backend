import uuid

from sqlalchemy import Column, String, DateTime, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()
class JobRequest(Base):
    __tablename__ = "job_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, index=True) # Or UUID
    status = Column(String, default="PENDING", index=True)
    input_payload = Column(JSON)  # Stores the text to analyze
    result_data = Column(JSON, nullable=True) # Stores vectors/NLP results
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
