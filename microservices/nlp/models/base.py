from abc import ABC, abstractmethod
from typing import List, Dict, Any, Union
from common.models.api.redis_models import Article, NLPOptions, NLPResult, SentenceScore


# Keep the old name as an alias so existing imports don't break during migration.
NLPComponent = "NLPComponent"  # replaced below


class ArticleProcessor(ABC):
    """
    Protocol for components that write directly to NLPResult.
    They do not consume or return a sentence list.
    Implementations: EntityRecognizer, BiasDetector.
    """
    @abstractmethod
    def run(self, article: Article, result: NLPResult, options: NLPOptions) -> None:
        """Executes component logic and writes into result in-place."""
        pass


class SentenceProcessor(ABC):
    """
    Protocol for components that transform the local sentence list.
    They may read from result but must not write to it.
    They receive and return List[SentenceScore].
    Implementations: Preprocessor, SentenceExtraction, Decontextualizer,
                     CheckWorthiness, Embedder.
    """
    @abstractmethod
    def run(
        self,
        article: Article,
        result: NLPResult,
        options: NLPOptions,
        sentences: List[SentenceScore],
    ) -> List[SentenceScore]:
        """Transforms the sentence list and returns the (possibly filtered) result."""
        pass


# NLPComponent is kept as the union type for ClaimExtraction's type annotations.
NLPComponent = Union[ArticleProcessor, SentenceProcessor]  # type: ignore[misc,assignment]

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
