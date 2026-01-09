from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

@dataclass
class ArticleInput:
    """The raw data received by the NLP service."""
    id: str
    text: str
    title: Optional[str] = None
    url: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class AnalysisOptions:
    """Toggles and thresholds to control the pipeline's execution."""
    enable_bias_detection: bool = True
    enable_ner: bool = True
    enable_centrality: bool = True
    enable_claim_extraction: bool = True
    max_claims: int = 10
    min_confidence: float = 0.5
    # If True, include high-dimensional embeddings in the final response
    return_embeddings: bool = True 

@dataclass
class SentenceScore:
    """Represents an individual sentence, its calculated importance, and its vector."""
    index: int
    text: str
    score: float = 0.0
    # The embedding for pgvector (e.g., 384 dimensions for all-MiniLM-L6-v2)
    embedding: Optional[List[float]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class Entity:
    """A named entity (Person, Organization, Location) found in the text."""
    text: str
    label: str  # e.g., "PER", "ORG", "GPE"
    start_char: int
    end_char: int

@dataclass
class BiasProfile:
    """Result of political and emotional bias analysis."""
    political_bias: str  # e.g., "Left", "Center", "Right"
    confidence: float
    scores: Dict[str, float]  # e.g., {"left": 0.1, "right": 0.8}
    emotional_tone: Optional[str] = None

@dataclass
class Claim:
    """A factual claim extracted for verification, ready for pgvector storage."""
    text: str
    confidence: float
    sentence_indices: List[int]
    # Decontextualized version of the claim (standalone sentence)
    contextualized_text: Optional[str] = None
    # Vector representation for semantic similarity search in the DB
    embedding: Optional[List[float]] = None

@dataclass
class AnalysisResult:
    """The aggregate object containing all insights produced by the pipeline."""
    article_id: str
    # Global document-level embedding (e.g., average of sentence embeddings)
    doc_embedding: Optional[List[float]] = None
    
    # Core outputs
    sentences: List[SentenceScore] = field(default_factory=list)
    claims: List[Claim] = field(default_factory=list)
    entities: List[Entity] = field(default_factory=list)
    bias_profile: Optional[BiasProfile] = None
    
    # Internal state / Metrics
    processing_time_ms: float = 0.0
    status: str = "initialized"
    metadata: Dict[str, Any] = field(default_factory=dict)