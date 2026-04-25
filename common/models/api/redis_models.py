import datetime
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel

from common.models.api.dtos.job import JobStage

"""
In redis, each message looks like this
            some redis_ID
                |
                V
        1730908200123-0 : {
            "payload": {
                "header": {
                    "message_id": "ab12...cd34",
                    "timestamp": "2025-11-06T22:30:00.123456",
                    "type": "background"
                },
                "data": {
                    "url": "http://example.com/article1",
                    "source_rss": "Example News Feed"
                }
            }
        }

"""




#redis message wraps a message/job object
@dataclass
class BiasProfile:
    """Result of political and emotional bias analysis."""
    bias_category: str  # e.g., "Left", "Center", "Right"
    bias_analysis_confidence: float
    sentiment_category: Optional[str] = None
    sentiment_analysis_confidence: float = 0.0

@dataclass
class NLPOptions:
    """Toggles and thresholds to control the pipeline's execution."""
    enable_bias_detection: bool = True
    enable_ner: bool = True
    enable_centrality: bool = True
    enable_claim_extraction: bool = True
    enable_decontextualization: bool = True
    max_claims: int = 10
    min_confidence: float = 0.50  # Matches CheckWorthinessFilter threshold in checkworthy.py
    # If True, include high-dimensional embeddings in the final response
    return_embeddings: bool = True
    
@dataclass(frozen=True)
class Article:
    link: str
    source: str | None = None
    title : str | None = None
    summary : str | None = None
    text: str | None = None
    
job_start_mono = time.monotonic()
class MessageTimestamp(BaseModel):
    """
    Represents the timestamp of a stage
    """
    job_uid: str
    stage_name: str
    wall_time: str
    offset_s: float
    
class MessageHeader(BaseModel):
    """
    Represents the basic information used to identify and get stats on Messages
    """

    id: int | None = None
    uid: str
    type: str
    status: str
    created_at: str



@dataclass
class ParseResult:
    text: str
    title: Optional[str]
    author: Optional[str]
    published_at: Optional[str]
    
    def __getitem__(self, key):
        return getattr(self, key, None)
    
    def __setitem__(self, key, value):
        if hasattr(self, key):
            setattr(self, key, value)
        else:
            raise KeyError(f"{key} is not a valid field")

        
@dataclass
class Entity:
    """A named entity (Person, Organization, Location) found in the text."""
    entity_text: str
    type_of_entity: str
    start_char: int
    end_char: int


@dataclass
class SentenceScore:
    """
    Represents an individual sentence, its calculated importance, and metadata.
    Acts as the primary unit of analysis in the pipeline.
    """
    index: int
    text: str # This holds the FINAL (Decontextualized) text
    original_text: Optional[str] = None # Stores raw text before rewriting
    
    # Centrality (LexRank)
    score: float = 0.0
    
    # Claim Verification Data
    is_checkworthy: bool = False
    claim_type: Optional[str] = None # e.g., "factual claim", "opinion"
    confidence: float = 0.0
    
    # Vector Embedding (MPNet: 768 dim)
    embedding: Optional[List[float]] = None
    
    # Linked Entities specific to this sentence
    entities: List[Entity] = field(default_factory=list)

    metadata: Dict[str, Any] = field(default_factory=dict)

    
@dataclass
class Claim:
    """
    A specific factual claim extracted for verification.
    This is usually a filtered subset of SentenceScore objects, formatted for DB storage.
    """
    confidence: float
    source_sentence_indices: List[int] # which sentences are used to form the claim
    decontextualised_claim_text: str
    decontextualised_claim_embedding: Optional[List[float]] = None
    NER_entities: List[Entity] = field(default_factory=list)


@dataclass
class bias_score:
    """Result of political and emotional bias analysis."""
    bias_category:Optional[str] # e.g., "Left", "Center", "Right"
    bias_analysis_confidence:Optional[float]
    sentiment_category:Optional[str]
    sentiment_analysis_confidence:Optional[float]


@dataclass
class NLPResult:
    """The aggregate object containing all insights produced by the pipeline."""
    claims_in_article: Optional[List[Claim]] = field(default_factory=list)
    entities_in_article: Optional[List[Entity]] = field(default_factory=list)
    bias_profile: Optional[BiasProfile] = None
    topic_label: Optional[str] = None
    topic_confidence: Optional[float] = None

@dataclass
class RetrievalResult:
    """The aggregate object containing all insights produced by the pipeline."""
    save_data_result: Dict[str, Any]
    save_job_result: Dict[str, Any]
    matches: List[Dict[str,Any]]
    related_articles: List[str]


class MessagePayload(BaseModel):
    """
    Represents the payload between ingestor and web scraper service
    """
    #initial request
    article_url: str    | None     = None
    #ingestion
    news_outlet: str    | None     = None
    title: str          | None     = None
    publish_date: str   | None     = None
    author: str         | None     = None
    summary: str        | None     = None
    #scrape
    raw_html: str       | None     = None
    parsed_text: str    | None     = None
    
    #nlp
    sentences: List[SentenceScore] = field(default_factory=list)
    claims_in_article: List[Claim] = field(default_factory=list)
    entities_in_article: List[Entity] = field(default_factory=list)
    bias_profile: Optional[BiasProfile] = None
    topic_label: Optional[str] = None
    topic_confidence: Optional[float] = None
    
    #retrieval
    save_data_result: Optional[Dict[str, Any]] = None
    save_job_result: Optional[Dict[str, Any]] = None
    matches: Any = None
    related_articles: Any = None
    
    
class Message(BaseModel):
    """
    Represents the actual message data type passed through a message queue
    """
    header: MessageHeader
    payload: MessagePayload
    stage_timestamps: List[MessageTimestamp]

@dataclass
class StreamMessage:
    # following fields are used for redis management
    stream: str
    redis_id: str
    priority: Union[int, float]
    
    # following field are the actual job keys
    data: Message # the actual message object, i.e the class above
    
    @property
    def header(self) -> Optional[MessageHeader]:
        return self.data.header
    
    @property
    def stage_timestamps(self) -> Optional[List[MessageTimestamp]]:
        return self.data.stage_timestamps

    @property
    def type(self) -> Optional[str]:
        return self.data.header.type
    
    @property
    def link(self) -> Optional[str]:
        return self.data.payload.article_url

    @property
    def html(self) -> Optional[str]:
        return self.data.payload.raw_html
    
    @property
    def text(self) -> Optional[str]:
        return self.data.payload.parsed_text
    
    @property
    def title(self) -> Optional[str]:
        return self.data.payload.title
    
    @property
    def publish_date(self) -> Optional[str]:
        return self.data.payload.publish_date
    
    @property
    def news_outlet_name(self) -> Optional[str]:
        return self.data.payload.news_outlet
    
    @property
    def all_claims(self) -> Optional[List[Claim]]:
        return self.data.payload.claims_in_article
    
    @property
    def all_entities(self) -> Optional[List[Entity]]:
        return self.data.payload.entities_in_article
    
    @property
    def bias_profile(self) -> Optional[BiasProfile]:
        return self.data.payload.bias_profile
    
    @property
    def uid(self) -> Optional[str]:
        return self.data.header.uid
    
    @property
    def retrieval_results(self) -> Optional[Dict[str, Any]]:
        
        result = {
                "save_data_result" : self.data.payload.save_data_result,
                "save_job_result": self.data.payload.save_job_result,
                "matches": self.data.payload.matches,
            "related_articles": self.data.payload.related_articles,
            "bias_profile": asdict(self.data.payload.bias_profile) if self.data.payload.bias_profile else None,
        }
        
        return result

    def set_raw_html(self, page_html: str) -> None:
        self.data.payload.raw_html = page_html
    
    def set_parsed_result(self, parsed_result: ParseResult) -> None:
        """Unpacks a ParseResult object and updates the message payload."""
        # Use dot notation on the ParseResult object for clarity and safety
        if parsed_result.text:
            self.data.payload.parsed_text = parsed_result.text
            
        if parsed_result.title:
            self.data.payload.title = parsed_result.title
            
        if parsed_result.author and not self.data.payload.author:
            self.data.payload.author = parsed_result.author
            
        if parsed_result.published_at and not self.data.payload.publish_date:
            self.data.payload.publish_date = parsed_result.published_at
    
    def create_nlp_result(self) -> NLPResult:
        return NLPResult(
            claims_in_article = self.data.payload.claims_in_article,
            entities_in_article = self.data.payload.entities_in_article,
            bias_profile = self.data.payload.bias_profile,
            topic_label = self.data.payload.topic_label,
            topic_confidence = self.data.payload.topic_confidence,
        )
    
    def set_nlp_result(self, nlp_result: NLPResult) -> None:
        """Unpacks a ParseResult object and updates the message payload."""
        # Use dot notation on the ParseResult object for clarity and safety
        # if not self.data.payload.sentences and nlp_result.sentences:
        #     self.data.payload.sentences = nlp_result.sentences

        if nlp_result.claims_in_article:
            self.data.payload.claims_in_article = nlp_result.claims_in_article
            
        if nlp_result.entities_in_article:
            self.data.payload.entities_in_article = nlp_result.entities_in_article
            
        if nlp_result.bias_profile:
            self.data.payload.bias_profile = nlp_result.bias_profile

        if nlp_result.topic_label is not None:
            self.data.payload.topic_label = nlp_result.topic_label
            self.data.payload.topic_confidence = nlp_result.topic_confidence

    def set_retrieval_result(self, retrieval_result: RetrievalResult) -> None:
        if retrieval_result.save_data_result:
            self.data.payload.save_data_result = retrieval_result.save_data_result
            
        if retrieval_result.save_job_result:
            self.data.payload.save_job_result = retrieval_result.save_job_result
        
        if isinstance(retrieval_result.matches, list):
            self.data.payload.matches = retrieval_result.matches
        
        if isinstance(retrieval_result.related_articles, list):
            self.data.payload.related_articles = retrieval_result.related_articles

    def add_timestamp(self, stage_name: JobStage) -> None:
        wall = datetime.datetime.now(datetime.timezone.utc)
        offset = time.monotonic() - job_start_mono

        timestamp_row = MessageTimestamp(
            job_uid = self.data.header.uid,
            stage_name = stage_name.value,
            wall_time = wall.isoformat(),
            offset_s = offset
        )

        self.data.stage_timestamps.append(timestamp_row)
        
def add_timestamp_to_message(message:Message, stage_name: JobStage) -> Message:
    wall = datetime.datetime.now(datetime.timezone.utc)
    offset = time.monotonic() - job_start_mono

    timestamp_row = MessageTimestamp(
        job_uid = message.header.uid,
        stage_name = stage_name.value,
        wall_time = wall.isoformat(),
        offset_s = offset
    )
    message.stage_timestamps.append(timestamp_row)
    return message
