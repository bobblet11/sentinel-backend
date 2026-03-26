from abc import ABC, abstractmethod
from typing import Any, Dict, List, Union

from common.models.api.redis_models import Article, NLPOptions, NLPResult, SentenceScore


class NLPComponent(ABC):
    """
    Abstract base class for all NLP pipeline stages (legacy interface).
    Components that write directly to NLPResult and accept
    (article, result, options) without a sentences list inherit from this.
    Kept for backward compatibility with CheckWorthinessFilter and other
    components that have not yet been migrated to ArticleProcessor.
    """

    @abstractmethod
    def run(self, article: Article, result: NLPResult, options: NLPOptions) -> None:
        """
        Executes the component logic and updates the shared NLPResult in-place.
        """
        pass


class ArticleProcessor(ABC):
    """
    Protocol for components that write directly to NLPResult.
    They do not consume or return a sentence list.
    Implementations: EntityRecognizer, BiasDetector, ClaimExtraction.
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
