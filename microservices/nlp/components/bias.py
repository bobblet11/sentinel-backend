from microservices.nlp.models.base import ZeroShotClassifier
from microservices.nlp.types import BiasProfile

class BiasAnalyzer:
    """
    Analyzes text to detect political or other forms of bias.
    """
    def __init__(self, classifier: ZeroShotClassifier):
        """
        Initializes the analyzer with a classifier model.
        """
        pass

    def run(self, text: str) -> BiasProfile:
        """
        Analyzes the text for bias.
        
        Args:
            text: The full text to analyze.
            
        Returns:
            A BiasProfile object containing the detected bias information.
        """
        pass
