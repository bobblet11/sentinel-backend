from typing import List, Dict, Any, Union
import logging

# Local imports
from models.base import NLPComponent
from schemas import ArticleInput, AnalysisResult, AnalysisOptions, Entity

logger = logging.getLogger(__name__)

# Type alias
NERModel = Any 

class EntityRecognizer(NLPComponent):
    """
    Identifies named entities in the text.
    """
    def __init__(self, ner_model: NERModel):
        """
        Initializes the recognizer with an NER model.
        Args:
            ner_model: The loaded HuggingFace NER pipeline.
        """
        self.ner_model = ner_model

    def run(self, article: ArticleInput, result: AnalysisResult, options: AnalysisOptions) -> None:
        """
        Extracts entities from the text and updates result.entities.
        """
        # 1. Get text
        text = getattr(article, 'text', getattr(article, 'content', ""))
        
        if not text:
            logger.warning("EntityRecognizer: No text found.")
            result.entities = []
            return

        try:
            # 2. Run Inference
            raw_entities = self.ner_model(text)
        except Exception as e:
            logger.error(f"NER inference failed: {e}")
            result.entities = []
            return

        # 3. Map to Schema (Excluding confidence)
        entities_list: List[Entity] = []
        
        for item in raw_entities:
            # item structure: {'entity_group': 'ORG', 'score': 0.98, 'word': 'Google', ...}
            entity = Entity(
                text=item['word'],
                label=item['entity_group'],
                # Removed confidence
                start_char=item['start'],
                end_char=item['end']
            )
            entities_list.append(entity)

        # 4. Update Result
        result.entities = entities_list
        logger.info(f"EntityRecognizer: Found {len(entities_list)} entities.")