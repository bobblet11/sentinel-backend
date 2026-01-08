from typing import Optional
from microservices.nlp.types import ArticleInput, AnalysisResult, AnalysisOptions
from microservices.nlp.registry import ModelRegistry

class SentinelNLP:
    """
    Main entry point for the Sentinel NLP microservice.
    Orchestrates the analysis pipeline.
    """
    def __init__(self, options: Optional[AnalysisOptions] = None):
        """
        Initialize the NLP service.
        
        Args:
            options: Global default options for analysis.
        """
        pass

    def warmup(self) -> None:
        """
        Preloads necessary models to ensure low latency on first request.
        """
        pass

    def analyze(self, article: ArticleInput, options: Optional[AnalysisOptions] = None) -> AnalysisResult:
        """
        Analyzes an article to extract claims, detect bias, and identify entities.
        
        Args:
            article: The article input containing text and metadata.
            options: Optional runtime overrides for analysis options.
            
        Returns:
            AnalysisResult containing all extracted insights.
        """
        pass

    def analyze_text(self, text: str, options: Optional[AnalysisOptions] = None) -> AnalysisResult:
        """
        Convenience method to analyze raw text without full article metadata.
        
        Args:
            text: Single string of text to analyze.
            options: Optional runtime overrides for analysis options.
            
        Returns:
            AnalysisResult containing all extracted insights.
        """
        pass
