from abc import ABC, abstractmethod
from typing import List, Dict, Any, Union
from schemas import ArticleInput, AnalysisResult, AnalysisOptions

class NLPComponent(ABC): 
    """
    Abstract base class for all NLP pipeline stages.
    Each component (NER, Bias, etc.) must implement 'run'.
    """
    @abstractmethod
    def run(self, article: ArticleInput, result: AnalysisResult, options: AnalysisOptions) -> None:
        """
        Executes the component logic and updates the shared AnalysisResult in-place.
        """
        pass

class SentenceEmbedder(ABC):
    """
    Interface for sentence embedding models.
    """
    @abstractmethod
    def encode(self, sentences: List[str]) -> Any:
        """
        Encodes a list of sentences into embeddings.
        """
        pass

class ZeroShotClassifier(ABC):
    """
    Interface for zero-shot classification models.
    """
    @abstractmethod
    def classify(self, text: str, labels: List[str]) -> Dict[str, float]:
        """
        Classifies text against a list of candidate labels.
        """
        pass

class NERModel(ABC):
    """
    Interface for Named Entity Recognition models.
    """
    @abstractmethod
    def predict(self, text: str) -> List[Dict[str, Any]]:
        """
        Extracts entities from the provided text.
        """
        pass

class Seq2SeqRewriter(ABC):
    """
    Interface for Sequence-to-Sequence rewriting models (e.g., decontextualization).
    """
    @abstractmethod
    def rewrite(self, text: str, context: str) -> str:
        """
        Rewrites the text usually to include missing context.
        """
        pass
