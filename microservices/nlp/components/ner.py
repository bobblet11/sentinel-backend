import logging
from typing import Any, List
from transformers import pipeline

# Local imports
from microservices.nlp.models.base import NLPComponent
from common.models.api.redis_models import Article, Entity, NLPOptions, NLPResult
from microservices.nlp.config import NER_MAX_TEXT_CHARS, NER_MODEL

logger = logging.getLogger(__name__)

class EntityRecognizer(NLPComponent):
    """
    Identifies named entities (PER, ORG, LOC, MISC) in the text.
    Uses 'dslim/bert-base-NER-uncased' to handle noisy/lowercase text robustly.
    """
    def __init__(self, ner_model: Any = None):
        """
        Args:
            ner_model: The loaded HuggingFace NER pipeline. 
        """
        if ner_model:
            self.ner_model = ner_model
        else:
            logger.info("EntityRecognizer: Loading model '%s'...", NER_MODEL)
            try:
                # We default to CPU (-1) for safety, but main.py/nlp_service should pass a GPU-loaded model
                self.ner_model = pipeline(
                    "token-classification", 
                    model=NER_MODEL,
                    aggregation_strategy="simple",
                    device=-1 
                )
            except Exception as e:
                logger.error(f"EntityRecognizer: Failed to load model: {e}")
                raise

    def run(self, article: Article, result: NLPResult, options: NLPOptions) -> None:
        """
        Extracts entities from the text and updates result.entities.
        """
        # We perform NER on the *Full Text* of the article for better context,
        # rather than sentence-by-sentence which is slow and loses context.
        text = getattr(article, 'text', "")
        
        if not text:
            return

        # Keep NER bounded on very long articles to prevent long CPU inference.
        safe_text = text[:NER_MAX_TEXT_CHARS]

        try:
            # Run Inference
            raw_entities = self.ner_model(safe_text)
            
        except Exception as e:
            logger.error(f"NER inference failed: {e}")
            return

        # Map to Schema
        entities_list: List[Entity] = []
        unique_hashes = set() # To avoid duplicates
        
        for item in raw_entities:
            # item: {'entity_group': 'ORG', 'score': 0.98, 'word': 'apple', 'start': 0, 'end': 5}
            
            # Confidence Threshold
            if item['score'] < options.min_confidence:
                continue

            # Create Entity Object
            entity = Entity(
                entity_text=item['word'],
                type_of_entity=item['entity_group'], # "PER", "ORG", "LOC", "MISC"
                start_char=item['start'],
                end_char=item['end']
            )
            
            # Deduplicate (e.g., don't list "Trump" 50 times)
            # We create a simple unique signature: "Trump|PER"
            entity_hash = f"{entity.entity_text.lower()}|{entity.type_of_entity}"
            
            if entity_hash not in unique_hashes:
                entities_list.append(entity)
                unique_hashes.add(entity_hash)

        # Update Result
        result.entities_in_article = entities_list
        logger.info(f"EntityRecognizer: Found {len(entities_list)} unique entities.")
