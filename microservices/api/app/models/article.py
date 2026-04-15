import uuid

from sqlalchemy import Column, ForeignKey, String, DateTime, Integer, Text, Float
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class SentimentAnalysis(Base):
    __tablename__ = "sentiment_analysis"
    id = Column(Integer, primary_key=True, autoincrement=True)
    bias_category = Column(String(50), nullable=True)
    bias_score = Column(Float, nullable=True)
    bias_analysis_confidence = Column(Float, nullable=True)
    sentiment_category = Column(String(50), nullable=True)
    sentiment_analysis_confidence = Column(Float, nullable=True)


class NewsOutlet(Base):
    __tablename__ = "news_outlet"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False, unique=True)
    articles = relationship("Article", back_populates="outlet")


class Article(Base):
    __tablename__ = "article"
    id = Column(Integer, primary_key=True, autoincrement=True)
    url = Column(String(250), nullable=False)  
    title = Column(String(1024), nullable=True)
    text = Column(Text, nullable=True)
    html = Column(Text, nullable=True)
    publishedAt = Column("publishedat", DateTime(timezone=True), nullable=True)
    outlet_id = Column(Integer, ForeignKey("news_outlet.id"), nullable=True)
    sentiment_id = Column(Integer, ForeignKey("sentiment_analysis.id"), nullable=True)
    author_id = Column(Integer, nullable=True)

    outlet = relationship("NewsOutlet", back_populates="articles")
    sentiment = relationship("SentimentAnalysis")
