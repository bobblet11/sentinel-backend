import logging
import torch
from transformers import AutoTokenizer, AutoModelForTokenClassification, pipeline
from typing import List, Dict, Any

# Local imports
from microservices.nlp.models.base import NLPComponent
from common.models.api.redis_models import Article, NLPOptions, NLPResult, Entity, SentenceScore
from microservices.nlp.config import NER_MODEL, NER_BATCH_SIZE

logger = logging.getLogger(__name__)

class EntityRecognizer(NLPComponent):
    """
    Named Entity Recognition using the model specified in config.NER_MODEL.

    Processes the sentences list and writes deduplicated entities
    into result.entities_in_article.
    """

    def __init__(self):
        self.model_name = NER_MODEL
        self.device = 0 if torch.cuda.is_available() else -1
        use_fp16 = torch.cuda.is_available()

        logger.info(f"EntityRecognizer: Loading '{self.model_name}' "
                    f"on {'CUDA' if self.device == 0 else 'CPU'} "
                    f"(fp16={use_fp16})...")
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            self.model = AutoModelForTokenClassification.from_pretrained(
                self.model_name,
                torch_dtype=torch.float16 if use_fp16 else torch.float32,
            )
            self.nlp_pipeline = pipeline(
                "ner",
                model=self.model,
                tokenizer=self.tokenizer,
                aggregation_strategy="simple",
                device=self.device,
                batch_size=NER_BATCH_SIZE,
            )
        except Exception as e:
            logger.error(f"EntityRecognizer: Failed to load model: {e}")
            raise

    def run(self, article: Article, result: NLPResult, options: NLPOptions,
            sentences: List[SentenceScore]) -> None:
        """
        Runs NER over all sentences provided by the Preprocessor.
        Updates result.entities_in_article with unique entities found.
        """
        if not sentences:
            logger.warning("EntityRecognizer: No sentences provided to process.")
            return

        # Filter out empty/whitespace-only texts to prevent pipeline errors
        texts: List[str] = [s.text for s in sentences if s.text and s.text.strip()]
        if not texts:
            logger.warning("EntityRecognizer: All sentence texts are empty, skipping.")
            return

        logger.info(f"EntityRecognizer: Running NER on {len(texts)} sentences.")

        # Dictionary to track unique entities by (text, label) to avoid duplicates
        unique_entities: Dict[tuple, Dict[str, Any]] = {}

        try:
            # Batch inference via Hugging Face pipeline
            for sent_results in self.nlp_pipeline(texts):
                for item in sent_results:
                    text = item["word"].strip()
                    label = item["entity_group"]
                    score = float(item["score"])

                    # Ignore noise or very short fragments
                    if len(text) < 3:
                        continue

                    key = (text.lower(), label)
                    # Keep the entity occurrence with the highest confidence score
                    if key not in unique_entities or score > unique_entities[key]["score"]:
                        e_obj = Entity(
                            entity_text=text,
                            type_of_entity=label,
                            start_char=item.get("start", 0),
                            end_char=item.get("end", 0),
                        )
                        unique_entities[key] = {"entity_obj": e_obj, "score": score}

            # Map results to the NLPResult object
            result.entities_in_article = [v["entity_obj"] for v in unique_entities.values()]
            logger.info(f"EntityRecognizer: Found {len(result.entities_in_article)} unique entities.")

        except Exception as e:
            logger.error(f"EntityRecognizer failed during execution: {e}")
            raise

if 'RUN_DEBUG_STEPS' in globals() and RUN_DEBUG_STEPS:
    print("\n--- Running Entity Recognizer Test ---")
    try:
        ner = EntityRecognizer()
        ner.run(article, result, options, sentences)

        print(f"Entities Extracted: {len(result.entities_in_article)}")
        for e in result.entities_in_article[:5]: # Show first 5
            print(f"  - {e.entity_text} [{e.type_of_entity}]")

    except Exception as e:
        import traceback
        print(f"Error during NER test: {e}")
        traceback.print_exc()