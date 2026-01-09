from typing import List, Tuple
from microservices.nlp.models.base import Seq2SeqRewriter, NLPComponent
from microservices.nlp.types import ArticleInput, AnalysisResult, AnalysisOptions

class Decontextualizer(NLPComponent):
    """
    Rewrites claims to be self-contained by resolving coreferences and adding context.
    """
    def __init__(self, rewriter: Seq2SeqRewriter):
        """
        Initializes the decontextualizer with a rewriter model.
        """
        pass

    def run(self, article: ArticleInput, result: AnalysisResult, options: AnalysisOptions) -> None:
        """
        Rewrites claims in result.claims to make them standalone.
        Updates result.claims in-place.
        
        Args:
            article: The article input (source of full context).
            result: The analysis result containing claims.
            options: Configuration options.
        """
        pass
