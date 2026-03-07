from sqlalchemy import (
    Column, Integer, String, Text, DateTime, ForeignKey, Float, Table, func, JSON
)
from sqlalchemy.orm import relationship, declarative_base
from pgvector.sqlalchemy import Vector
Base = declarative_base()

claim_to_entity_table = Table(
    "claim_to_entity",
    Base.metadata,
    Column("entity_id", Integer, ForeignKey("entity.id"), primary_key=True),
    Column("claim_id", Integer, ForeignKey("claim.id"), primary_key=True),
)

class Entity(Base):
    __tablename__ = "entity"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False, index=True)
    type = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    claims = relationship("Claim", secondary=claim_to_entity_table, back_populates="entities")


class Claim(Base):
    __tablename__ = "claim"
    id = Column(Integer, primary_key=True, autoincrement=True)
    original_sentence = Column(Text, nullable=False)
    decontextualised_claim = Column(Text, nullable=True)
    decontextualised_embedding = Column(Vector(768), nullable=True)
    centrality_score = Column(Float, nullable=True)
    article_id = Column(Integer, ForeignKey("article.id"), nullable=False)

    article = relationship("Article", back_populates="claims")
    entities = relationship("Entity", secondary=claim_to_entity_table, back_populates="claims")


class NewsOutlet(Base):
    __tablename__ = "news_outlet"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False, unique=True)

    articles = relationship("Article", back_populates="outlet")


class Author(Base):
    __tablename__ = "author"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False, unique=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Article(Base):
    __tablename__ = "article"
    id = Column(Integer, primary_key=True, autoincrement=True)
    url = Column(String(1024), nullable=False, unique=True)
    title = Column(String(1024), nullable=True)
    text = Column(Text, nullable=True)
    html = Column(Text, nullable=True)
    publishedAt = Column('publishedat', DateTime(timezone=True), nullable=True)
    sentiment_id = Column(Integer, ForeignKey("sentiment_analysis.id"), nullable=True)
    outlet_id = Column(Integer, ForeignKey("news_outlet.id"), nullable=True)

    sentiment = relationship("SentimentAnalysis", back_populates="article")
    outlet = relationship("NewsOutlet", back_populates="articles")
    claims = relationship("Claim", back_populates="article")


class SentimentAnalysis(Base):
    __tablename__ = "sentiment_analysis"
    id = Column(Integer, primary_key=True, autoincrement=True)
    bias_category = Column(String(50), nullable=True)
    bias_score = Column(Float, nullable=True)
    bias_analysis_confidence = Column(Float, nullable=True)
    sentiment_category = Column(String(50), nullable=True)
    sentiment_analysis_confidence = Column(Float, nullable=True)
    article = relationship("Article", back_populates="sentiment")


class Job(Base):
    __tablename__ = "job"
    id = Column(Integer, primary_key=True, autoincrement=True)
    uid = Column(String(36), nullable=True)  # uuid text
    status = Column(String(50), nullable=True)
    type = Column(String(50), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    article_id = Column(Integer, ForeignKey("article.id"), nullable=False)


class JobTimestamp(Base):
    __tablename__ = "job_timestamp"
    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(Integer, ForeignKey("job.id"), nullable=False)
    stage_name = Column(String(255), nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
