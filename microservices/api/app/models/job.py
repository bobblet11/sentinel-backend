import uuid

from sqlalchemy import Column, ForeignKey, String, DateTime, JSON, Integer, UUID
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.ext.declarative import declarative_base

from microservices.api.app.dtos.job import JobType, JobStatus

Base = declarative_base()
class Job(Base):
    __tablename__ = "job"
    id = Column(Integer, primary_key=True, autoincrement=True)
    uid = Column(UUID, nullable=False)  
    article_id = Column(Integer, nullable=False)  
    type = Column(String(20), nullable=False, default=JobType.BACKGROUND.value)  
    status = Column(String(50), nullable=False, default=JobStatus.PENDING.value)  
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

class JobTimestamp(Base):
    __tablename__ = "job_timestamp"

    id = Column(Integer, primary_key=True, autoincrement=True)  
    job_id = Column(Integer, ForeignKey("job.id", ondelete="CASCADE"), nullable=False)
    stage_name = Column(String, nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
