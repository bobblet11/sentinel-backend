from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ArticleInput:
    """The raw data received by the NLP service."""

    text: str
    title: Optional[str] = None
    url: Optional[str] = None


@dataclass
class Entity:
    """A named entity (Person, Organization, Location) found in the text."""

    text: str
    label: str  # e.g., "PER", "ORG", "GPE"
    start_char: int
    end_char: int


@dataclass
class SentenceScore:
    """
    Represents an individual sentence, its calculated importance, and metadata.
    Acts as the primary unit of analysis in the pipeline.
    """

    index: int
    text: str  # This holds the FINAL (Decontextualized) text
    original_text: Optional[str] = None  # Stores raw text before rewriting

    # Centrality (LexRank)
    score: float = 0.0

    # Claim Verification Data
    is_checkworthy: bool = False
    claim_type: Optional[str] = None  # e.g., "factual claim", "opinion"
    confidence: float = 0.0

    # Vector Embedding (MPNet: 768 dim)
    embedding: Optional[List[float]] = None

    # Linked Entities specific to this sentence
    entities: List[Entity] = field(default_factory=list)

    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BiasProfile:
    """Result of political and emotional bias analysis."""

    bias_category: str  # e.g., "Left", "Center", "Right"
    bias_analysis_confidence: float
    sentiment_category: Optional[str] = None
    sentiment_analysis_confidence: float = 0.0


@dataclass
class Claim:
    """
    A specific factual claim extracted for verification.
    This is usually a filtered subset of SentenceScore objects, formatted for DB storage.
    """

    text: str
    confidence: float
    sentence_indices: List[int]

    # Decontextualized version (if different from text)
    contextualized_text: Optional[str] = None

    # Vector representation for semantic similarity search in the DB
    embedding: Optional[List[float]] = None

    # Entities found in this specific claim
    entities: List[Entity] = field(default_factory=list)


@dataclass
class AnalysisResult:
    """The aggregate object containing all insights produced by the pipeline."""

    # Global document-level embedding (e.g., average of sentence embeddings)
    doc_embedding: Optional[List[float]] = None

    # Core outputs
    sentences: List[SentenceScore] = field(default_factory=list)
    claims: List[Claim] = field(default_factory=list)

    # Global Entity List (deduplicated)
    entities: List[Entity] = field(default_factory=list)

    bias_profile: Optional[BiasProfile] = None

    # Processing Metadata (e.g. latency, model versions)
    processing_metadata: Dict[str, Any] = field(default_factory=dict)
