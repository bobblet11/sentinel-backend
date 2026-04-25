from abc import ABC, abstractmethod
from typing import Any, Dict, List

from common.models.api.redis_models import (
    Article,
    NLPOptions,
    NLPResult,
    SentenceScore,
    StreamMessage,
)


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


class ArticleProcessor(ABC):
    """
    Protocol for components that write directly to NLPResult.
    They do not consume or return a sentence list.
    Implementations: EntityRecognizer, BiasDetector, ClaimExtraction.
    """

    @abstractmethod
    def run(
        self, article: Article, message: StreamMessage, options: NLPOptions
    ) -> None:
        """Executes component logic and writes into result in-place."""


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
        message: StreamMessage,
        options: NLPOptions,
        sentences: List[SentenceScore],
    ) -> List[SentenceScore]:
        """Transforms the sentence list and returns the (possibly filtered) result."""


class SentenceEmbedder(ABC):
    """
    Interface for sentence embedding models.
    """

    @abstractmethod
    def encode(self, sentences: List[str]) -> Any:
        """
        Encodes a list of sentences into embeddings.
        """


class ZeroShotClassifier(ABC):
    """
    Interface for zero-shot classification models.
    """

    @abstractmethod
    def classify(self, text: str, labels: List[str]) -> Dict[str, float]:
        """
        Classifies text against a list of candidate labels.
        """


class NERModel(ABC):
    """
    Interface for Named Entity Recognition models.
    """

    @abstractmethod
    def predict(self, text: str) -> List[Dict[str, Any]]:
        """
        Extracts entities from the provided text.
        """


class Seq2SeqRewriter(ABC):
    """
    Interface for Sequence-to-Sequence rewriting models (e.g., decontextualization).
    """

    @abstractmethod
    def rewrite(self, text: str, context: str) -> str:
        """
        Rewrites the text usually to include missing context.
        """
