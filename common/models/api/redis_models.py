import datetime
from datetime import timezone
import time
from typing import Any, List, Union, Dict, Optional
from dataclasses import dataclass, field
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
class NLPOptions:
    """Toggles and thresholds to control the pipeline's execution."""
    enable_bias_detection: bool = True
    enable_ner: bool = True
    enable_centrality: bool = True
    enable_claim_extraction: bool = True
    max_claims: int = 10
    min_confidence: float = 0.75 # Updated default to match CheckWorthinessFilter
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
class SentenceScore:
    """
    Represents a sentence and its analysis scores across the pipeline.
    """
    index: int
    text: str
    score: float = 0.0  # Centrality or relevance score
    embedding: Optional[List[float]] = None  # Vector representation
    label: Optional[str] = None  # e.g., "CLAIM", "BIASED", "NEUTRAL"

    
@dataclass
class Claim:
    """
    A specific factual claim extracted for verification.
    This is usually a filtered subset of SentenceScore objects, formatted for DB storage.
    """
    confidence: float
    source_sentence_indices: List[int] # which sentences are used to form the claim
    contextualised_claim_text: str
    decontextualised_claim_text: Optional[str] = None
    decontextualised_claim_embedding: Optional[List[float]] = None
    NER_entities: List[Entity] = field(default_factory=list)


@dataclass
class BiasProfile:
    """Result of political and emotional bias analysis."""
    political_bias: str  # e.g., "Left", "Center", "Right"
    confidence: float
    scores: Dict[str, float]  # e.g., {"left": 0.1, "right": 0.8}
    emotional_tone: Optional[str] = None


@dataclass
class NLPResult:
    """The aggregate object containing all insights produced by the pipeline."""
    sentences: List[SentenceScore] = field(default_factory=list)
    claims_in_article: List[Claim] = field(default_factory=list)
    entities_in_article: List[Entity] = field(default_factory=list)
    bias_profile: Optional[BiasProfile] = None

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
    def all_claims(self) -> Optional[List[Claim]]:
        return self.data.payload.claims_in_article
    
    @property
    def all_entities(self) -> Optional[List[Entity]]:
        return self.data.payload.entities_in_article
    
    @property
    def bias_result(self) -> Optional[BiasProfile]:
        return self.data.payload.bias_profile

    
    def set_raw_html(self, page_html: str) -> None:
        self.data.payload.raw_html = page_html
    
    def set_parsed_result(self, parsed_result: ParseResult) -> None:
        """Unpacks a ParseResult object and updates the message payload."""
        # Use dot notation on the ParseResult object for clarity and safety
        if not self.data.payload.parsed_text and parsed_result.text:
            self.data.payload.parsed_text = parsed_result.text
            
        if not self.data.payload.title and parsed_result.title:
            self.data.payload.title = parsed_result.title
            
        if not self.data.payload.author and parsed_result.author:
            self.data.payload.author = parsed_result.author
            
        if not self.data.payload.publish_date and parsed_result.published_at:
            self.data.payload.publish_date = parsed_result.published_at
            
    def set_nlp_result(self, nlp_result: NLPResult) -> None:
        """Unpacks a ParseResult object and updates the message payload."""
        # Use dot notation on the ParseResult object for clarity and safety
        if not self.data.payload.sentences and nlp_result.sentences:
            self.data.payload.sentences = nlp_result.sentences

        if not self.data.payload.claims_in_article and nlp_result.claims_in_article:
            self.data.payload.claims_in_article = nlp_result.claims_in_article
            
        if not self.data.payload.entities_in_article and nlp_result.entities_in_article:
            self.data.payload.entities_in_article = nlp_result.entities_in_article
            
        if not self.data.payload.bias_profile and nlp_result.bias_profile:
            self.data.payload.bias_profile = nlp_result.bias_profile
            
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
