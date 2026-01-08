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

@dataclass
class SentenceScore:
    """
    Represents a score assigned to a specific sentence, e.g., centrality or check-worthiness.
    """
    sentence_index: int
    text: str
    score: float
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
    article_id: Optional[str]
    claims: List[Claim]
    summary: Optional[str]
    bias_profile: Optional[BiasProfile]
    entities: List[Dict[str, Any]]
    processing_time_ms: float
