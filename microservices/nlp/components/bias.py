import logging
from microservices.nlp.models.base import NLPComponent
from common.models.api.redis_models import Article, BiasProfile, NLPOptions, NLPResult

logger = logging.getLogger(__name__)

class BiasDetector(NLPComponent):
    """
    detects bias in the text (DUMMY IMPLEMENTATION).
    """
    def __init__(self, model=None):
        """
        Initializes with a model (ignored for now).
        """
        self.model = model

    def run(self, article: Article, result: NLPResult, options: NLPOptions) -> None:
        """
        Populates result with dummy bias scores.
        """
        logger.info("BiasDetector: Running in DUMMY mode.")

        # 1. Dummy Sentence Scores
        # Iterate over sentences already split by the Preprocessor
        if result.sentences:
            for i, sentence in enumerate(result.sentences):
                # Assign a fake score (alternating low/high for variety)
                # 0.1 for even indices, 0.8 for odd indices
                dummy_score = 0.8 if i % 2 != 0 else 0.1
                
                sentence.score = dummy_score
                # sentence.label = "BIASED" if dummy_score > 0.5 else "NEUTRAL" # If label field exists on SentenceScore

        # 2. Dummy Global Bias Profile
        # Create a BiasProfile with hardcoded values
        dummy_profile = BiasProfile(
            political_bias="Center", 
            confidence=0.15,
            scores={"left": 0.4, "center": 0.2, "right": 0.4},
            emotional_tone="Neutral"
        )
        
        # 3. Update Result
        result.bias_profile = dummy_profile
        
        logger.info("BiasDetector: Populated dummy bias profile and sentence scores.")
