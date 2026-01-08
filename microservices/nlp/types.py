from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

@dataclass
class ArticleInput:
    """
    Represents the input data for an article to be analyzed.
    """
    id: str
    text: str
    title: Optional[str] = None
    url: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class AnalysisOptions:
    """
    Configuration options for a specific analysis run.
    """
    enable_bias_detection: bool = True
    enable_ner: bool = True
    max_claims: int = 10
    min_confidence: float = 0.5
    return_embeddings: bool = False

@dataclass
class SentenceScore:
    """
    Represents a score assigned to a specific sentence, e.g., centrality or check-worthiness.
    """
    sentence_index: int
    text: str
    score: float
    embedding: Optional[List[float]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class Claim:
    """
    Represents a specific claim extracted from the text.
    """
    text: str
    confidence: float
    sentence_indices: List[int]
    context: Optional[str] = None
    embedding: Optional[List[float]] = None

@dataclass
class BiasProfile:
    """
    Represents the detected bias profile of the text.
    """
    political_bias: str
    confidence: float
    scores: Dict[str, float]

@dataclass
class AnalysisResult:
    """
    The aggregate result of the NLP analysis pipeline.
    """
    article_id: Optional[str] = None
    claims: List[Claim] = field(default_factory=list)
    summary: Optional[str] = None
    bias_profile: Optional[BiasProfile] = None
    entities: List[Dict[str, Any]] = field(default_factory=list)
    processing_time_ms: float = 0.0
    document_embedding: Optional[List[float]] = None
