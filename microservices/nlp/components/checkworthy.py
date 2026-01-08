from typing import List
from microservices.nlp.models.base import ZeroShotClassifier
from microservices.nlp.types import Claim

class CheckWorthinessFilter:
    """
    Filters claims to retain only those that are factual and worth checking.
    """
    def __init__(self, classifier: ZeroShotClassifier):
        """
        Initializes the filter with a classifier model.
        """
        pass

    def run(self, claims: List[Claim]) -> List[Claim]:
        """
        Filters out subjective statements and opinions.
        
        Args:
            claims: List of candidate claims.
            
        Returns:
            List of claims deemed check-worthy.
        """
        pass
