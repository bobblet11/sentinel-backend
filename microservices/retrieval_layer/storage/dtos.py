from dataclasses import dataclass, field
from typing import List, Optional

from common.models.api.redis_models import Entity, MessageTimestamp


@dataclass
class CreateOrModifyArticle:
    article_url: str
    article_title: Optional[str] = None
    article_text: Optional[str] = None
    article_html: Optional[str] = None
    publish_date: Optional[str] = None
    author: Optional[str] = None


@dataclass
class CreateOrModifyOutlet:
    name: Optional[str] = None
    leaning: str = "Unknown"


@dataclass
class CreateOrModifySentiment:
    bias_category: Optional[str] = None
    bias_analysis_confidence: Optional[float] = None
    sentiment_category: Optional[str] = None
    sentiment_analysis_confidence: Optional[float] = None


@dataclass
class CreateOrModifyClaim:
    original_sentence: Optional[str] = None
    decontextualised_claim: Optional[str] = None
    decontextualised_embedding: Optional[List[float]] = None
    centrality_score: Optional[float] = None
    NER_entities: List[Entity] = field(default_factory=list)


@dataclass
class UpdateJob:
    job_id: int
    job_uid: str
    status: str
    stage_timestamps: List[MessageTimestamp]


@dataclass
class Evidence:
    id: str
    title: str
    source: str
    url: str
    bias: str
    publishedAt: str
    excerpt: str


@dataclass
class UpsertArticleTopic:
    article_id: int
    topic_label: str
    topic_confidence: float
