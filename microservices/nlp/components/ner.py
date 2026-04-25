import logging
from typing import Any, Dict, List, Optional

from transformers import (AutoModelForTokenClassification, AutoTokenizer,
                          pipeline)

from common.models.api.redis_models import (Article, Entity, NLPOptions,
                                            SentenceScore, StreamMessage)
from microservices.nlp.components.device import DeviceConfig
from microservices.nlp.config import NER_BATCH_SIZE, NER_MODEL
# Local imports
from microservices.nlp.models.base import ArticleProcessor

logger = logging.getLogger(__name__)

class EntityRecognizer(ArticleProcessor):
    """
    Named Entity Recognition using the model specified in config.NER_MODEL.

    Processes the sentences list and writes deduplicated entities
    into result.entities_in_article.
    """

    def __init__(self, device_config: DeviceConfig, model_manager: Optional[Any] = None):
        self.model_name = NER_MODEL
        self.device_id = device_config.device_id
        self.device = device_config.device

        logger.info(f"EntityRecognizer: Loading '{self.model_name}' "
                    f"on {device_config.device.upper()} "
                    f"(fp16={device_config.use_fp16})...")
        try:
            if model_manager is not None:
                from common.model_manager.registry import ModelState

                ner_state = model_manager.get_state("NER")
                if ner_state == ModelState.READY:
                    self.nlp_pipeline = model_manager.get("NER")
                    logger.info("EntityRecognizer: Using pipeline from ModelManager.")
                    return
                else:
                    logger.warning(
                        "EntityRecognizer: ModelManager NER state is %s, "
                        "falling back to direct load.",
                        ner_state.value,
                    )

            self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            self.model = AutoModelForTokenClassification.from_pretrained(
                self.model_name,
                torch_dtype=device_config.dtype,
                # Prevent Accelerate/transformers from initializing weights on the
                # `meta` device (common when device_map is used or memory-saver
                # paths are enabled), which breaks CPU execution.
                low_cpu_mem_usage=False,
            )
            self.model.to(self.device)
            self.model.eval()
            self.nlp_pipeline = pipeline(
                "ner",
                model=self.model,
                tokenizer=self.tokenizer,
                aggregation_strategy="simple",
                batch_size=NER_BATCH_SIZE,
            )
        except Exception as e:
            logger.error(f"EntityRecognizer: Failed to load model: {e}")
            raise

    def run(self, article: Article, message: StreamMessage, options: NLPOptions,
            sentences: List[SentenceScore]) -> None:
        """
        Runs NER over all sentences provided by the Preprocessor.
        Updates result.entities_in_article with unique entities found.
        Character offsets stored in Entity are article-relative.
        """
        if not sentences:
            logger.warning("EntityRecognizer: No sentences provided to process.")
            return

        # Filter out empty/whitespace-only texts, preserving sentence-level offsets.
        valid_sentences: List[SentenceScore] = [
            s for s in sentences if s.text and s.text.strip()
        ]
        if not valid_sentences:
            logger.warning("EntityRecognizer: All sentence texts are empty, skipping.")
            return

        texts: List[str] = [s.text for s in valid_sentences]
        logger.info(f"EntityRecognizer: Running NER on {len(texts)} sentences.")

        # Build cumulative char offsets so entity positions become article-relative.
        char_offsets: List[int] = []
        offset = 0
        for t in texts:
            char_offsets.append(offset)
            offset += len(t) + 1  # +1 for the sentence separator

        # Dictionary to track unique entities by (text, label) to avoid duplicates
        unique_entities: Dict[tuple, Dict[str, Any]] = {}

        try:
            # Batch inference via Hugging Face pipeline
            for sent_idx, sent_results in enumerate(self.nlp_pipeline(texts)):
                sent_offset = char_offsets[sent_idx]
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
                            start_char=sent_offset + item.get("start", 0),
                            end_char=sent_offset + item.get("end", 0),
                        )
                        unique_entities[key] = {"entity_obj": e_obj, "score": score}

            # Map results to the NLPResult object
            result = message.create_nlp_result()
            result.entities_in_article = [v["entity_obj"] for v in unique_entities.values()]
            logger.info(f"EntityRecognizer: Found {len(result.entities_in_article)} unique entities.")
            message.set_nlp_result(result)

        except Exception as e:
            logger.error(f"EntityRecognizer failed during execution: {e}")
            raise
