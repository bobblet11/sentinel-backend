from typing import List
from microservices.nlp.types import Claim
from microservices.nlp.models.base import SentenceEmbedder

class ClaimDeduplicator:
    """
    Deduplicates semantically similar claims.
    """
    def __init__(self, embedder: SentenceEmbedder):
        """
        Initializes the deduplicator with an embedding model.
        """
        pass

    def run(self, claims: List[Claim]) -> List[Claim]:
        """
        Removes duplicate claims based on semantic similarity.
        
        Args:
            claims: List of potential claims.
            
        Returns:
            List of unique claims.
        """
        pass
