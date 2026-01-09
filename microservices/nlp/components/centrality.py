from typing import List
from microservices.nlp.models.base import SentenceEmbedder, NLPComponent
from microservices.nlp.types import ArticleInput, AnalysisResult, AnalysisOptions

class CentralityScorer(NLPComponent):
    """
    Scores sentences based on their centrality/importance to the overall text.
    """
    def __init__(self, embedder: SentenceEmbedder):
        """
        Initializes the scorer with an embedding model.
        """
        pass

    def run(self, article: ArticleInput, result: AnalysisResult, options: AnalysisOptions) -> None:
        """
        Calculates centrality scores and embeddings for sentences in result.sentences.
        Updates result.sentences in-place.
        
        Args:
            article: The article input.
            result: The analysis result containing sentences to score.
            options: Configuration options.
        """
        pass
