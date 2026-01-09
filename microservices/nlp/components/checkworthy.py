from typing import List
from microservices.nlp.models.base import ZeroShotClassifier, NLPComponent
from microservices.nlp.types import ArticleInput, AnalysisResult, AnalysisOptions

class CheckWorthinessFilter(NLPComponent):
    """
    Filters claims to retain only those that are factual and worth checking.
    """
    def __init__(self, classifier: ZeroShotClassifier):
        """
        Initializes the filter with a classifier model.
        """
        pass

    def run(self, article: ArticleInput, result: AnalysisResult, options: AnalysisOptions) -> None:
        """
        Filters result.claims to retain only check-worthy ones.
        Updates result.claims in-place.
        
        Args:
            article: The article input (context).
            result: The analysis result containing claims.
            options: Configuration options.
        """
        pass
