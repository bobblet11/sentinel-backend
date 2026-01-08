from typing import List
from microservices.nlp.models.base import SentenceEmbedder
from microservices.nlp.types import SentenceScore

class CentralityScorer:
    """
    Scores sentences based on their centrality/importance to the overall text.
    """
    def __init__(self, embedder: SentenceEmbedder):
        """
        Initializes the scorer with an embedding model.
        """
        pass

    def run(self, sentences: List[str]) -> List[SentenceScore]:
        """
        Calculates centrality scores for each sentence.
        
        Args:
            sentences: List of sentences to score.
            
        Returns:
            List of SentenceScore objects containing the score for each sentence.
        """
        pass
