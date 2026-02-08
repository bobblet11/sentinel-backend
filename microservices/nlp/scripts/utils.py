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
    enable_bias_detection: bool = False
    enable_ner: bool = True
    enable_centrality: bool = True
    enable_claim_extraction: bool = True
    max_claims: int = 10
    # Lowered default for better recall on factual news reporting
    min_confidence: float = 0.60 
    return_embeddings: bool = True 

@dataclass
class Entity:
    """A named entity (Person, Organization, Location) found in the text."""
    text: str
    label: str  # e.g., "PER", "ORG", "LOC"
    start_char: int
    end_char: int

@dataclass
class SentenceScore:
    """
    Primary unit of analysis. 
    Updated to support decontextualization auditing and Three-Gate filtering.
    """
    index: int
    text: str # This holds the FINAL (processed) text
    original_text: Optional[str] = None # Stores raw text before rewriting
    
    # Centrality (LexRank)
    score: float = 0.0
    
    # Claim Classification Metadata
    is_checkworthy: bool = False
    claim_type: Optional[str] = None # e.g., "factual news reporting"
    confidence: float = 0.0
    
    # Vector Representation
    embedding: Optional[List[float]] = None
    
    # Metadata for debugging (e.g., "override_reason": "Centrality+Numbers")
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class Claim:
    """
    A specific factual claim extracted for verification.
    Formatted for pgvector storage in the Evidence Corpus.
    """
    text: str
    confidence: float
    sentence_index: int
    # Standing alone version after Decontextualization
    contextualized_text: Optional[str] = None
    embedding: Optional[List[float]] = None
    # Deduplicated entities specific to this claim
    entities: List[str] = field(default_factory=list)

@dataclass
class AnalysisResult:
    """Aggregate object produced by the pipeline."""
    article_id: str
    doc_embedding: Optional[List[float]] = None
    
    # Results
    sentences: List[SentenceScore] = field(default_factory=list)
    claims: List[Claim] = field(default_factory=list)
    entities: List[Entity] = field(default_factory=list)
    
    # Processing stats
    processing_metadata: Dict[str, Any] = field(default_factory=dict)