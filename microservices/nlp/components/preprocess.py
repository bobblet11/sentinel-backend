from typing import List
from microservices.nlp.models.base import NLPComponent
from microservices.nlp.types import ArticleInput, AnalysisResult, AnalysisOptions, SentenceScore

class Preprocessor(NLPComponent):
    """
    Handles text cleaning and sentence splitting.
    """
    def __init__(self):
        """
        Initializes the preprocessor.
        """
        pass

    def run(self, article: ArticleInput, result: AnalysisResult, options: AnalysisOptions) -> None:
        """
        Cleans the input text, splits it into sentences, and populates result.sentences.
        
        Args:
            article: The article input containing text.
            result: The analysis result to update (sentences).
            options: Configuration options.
        """
        pass
