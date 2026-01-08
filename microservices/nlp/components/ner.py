from typing import List, Dict, Any
from microservices.nlp.models.base import NERModel

class EntityRecognizer:
    """
    Identifies named entities in the text.
    """
    def __init__(self, ner_model: NERModel):
        """
        Initializes the recognizer with an NER model.
        """
        pass

    def run(self, text: str) -> List[Dict[str, Any]]:
        """
        Extracts entities from the text.
        
        Args:
            text: The text to analyze.
            
        Returns:
            List of detected entities with their metadata.
        """
        pass
