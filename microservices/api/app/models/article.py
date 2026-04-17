import uuid

from sqlalchemy import Column, ForeignKey, String, DateTime, Integer, Text, Float
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class NewsOutlet(Base):
    __tablename__ = "news_outlet"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False, unique=True)
    articles = relationship("Article", back_populates="outlet")


class Topic(Base):
    __tablename__ = "topic"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True)

    article_topics = relationship("ArticleTopic", back_populates="topic")


class ArticleTopic(Base):
    __tablename__ = "article_topic"
    id = Column(Integer, primary_key=True, autoincrement=True)
    article_id = Column(Integer, ForeignKey("article.id", ondelete="CASCADE"), nullable=False, unique=True)
    topic_id = Column(Integer, ForeignKey("topic.id"), nullable=False)
    confidence = Column(Float, nullable=False)

    topic = relationship("Topic", back_populates="article_topics")
    article = relationship("Article", back_populates="topic_assignment")


class Article(Base):
    __tablename__ = "article"
    id = Column(Integer, primary_key=True, autoincrement=True)
    url = Column(String(250), nullable=False)
    title = Column(String(1024), nullable=True)
    text = Column(Text, nullable=True)
    html = Column(Text, nullable=True)
    publishedAt = Column("publishedat", DateTime(timezone=True), nullable=True)
    outlet_id = Column(Integer, ForeignKey("news_outlet.id"), nullable=True)

    outlet = relationship("NewsOutlet", back_populates="articles")
    topic_assignment = relationship("ArticleTopic", back_populates="article", uselist=False)
