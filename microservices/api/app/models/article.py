import uuid

from sqlalchemy import Column, ForeignKey, String, DateTime, JSON, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.ext.declarative import declarative_base

from microservices.api.app.dtos.job import JobType, JobStatus

Base = declarative_base()
class Article(Base):
    __tablename__ = "article"
    id = Column(Integer, primary_key=True, autoincrement=True)
    url = Column(String(250), nullable=False)  
    html = Column(Text, nullable=True)  
    text = Column(Text, nullable=True)  
