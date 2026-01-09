# microservices/nlp/nlp_service.py
from typing import Optional, List
from microservices.nlp.types import ArticleInput, AnalysisResult, AnalysisOptions
from microservices.nlp.models.base import NLPComponent

# We will implement these empty skeletons in the next step
from microservices.nlp.components.preprocess import Preprocessor
from microservices.nlp.components.centrality import CentralityScorer
from microservices.nlp.components.bias import BiasDetector
from microservices.nlp.components.ner import EntityRecognizer
from microservices.nlp.components.checkworthy import ClaimExtractor

class SentinelNLP:
    def __init__(self, options: Optional[AnalysisOptions] = None):
        self.default_options = options or AnalysisOptions()
        
        # Define the execution order of the pipeline
        self.pipeline: List[NLPComponent] = [
            Preprocessor(),
            CentralityScorer(),
            BiasDetector(),
            EntityRecognizer(),
            ClaimExtractor()
        ]

    def analyze(self, article: ArticleInput, options: Optional[AnalysisOptions] = None) -> AnalysisResult:
        """
        The main orchestrator that passes the article through each pipeline stage.
        """
        current_options = options or self.default_options
        
        # Initialize the result container
        result = AnalysisResult(article_id=article.id)
        result.status = "processing"

        # Execute each stage sequentially
        for component in self.pipeline:
            try:
                # Components modify 'result' in-place (e.g. adding claims or entities)
                component.run(article, result, current_options)
            except Exception as e:
                # Log the error but allow the rest of the pipeline to attempt completion
                print(f"Pipeline error in {component.__class__.__name__}: {str(e)}")
                continue

        result.status = "completed"
        return result