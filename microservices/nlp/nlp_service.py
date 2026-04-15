# microservices/nlp/nlp_service.py
from datetime import datetime
from typing import Dict, List, Optional
from logging import getLogger
import random
from common.io.json_updater import JsonHandler
from common.models.api.dtos.job import JobType
from common.models.api.validation_helpers import get_pretty_print_stream_message, validate_after_nlp
import torch

from common.models.api.redis_models import (
    Article,
    BiasProfile,
    Claim,
    Entity,
    NLPOptions,
    NLPResult,
    SentenceScore,
    StreamMessage,
)
from common.service.service_template import ProcessingError, ServiceConfig, ServiceTemplate

from microservices.nlp.components.claimextract import ClaimExtraction
from microservices.nlp.config import (
    DEVICE_CONFIG,
    DUMMY_NLP_MODE,
    ENABLE_DECONTEXTUALIZATION,
    model_manager,
)

logger = getLogger("NLP")
EMBEDDING_DIM = 768

# ClaimExtraction is the sole pipeline orchestrator. It wires all 8 stages:
#   Stage 1:   Preprocessor         — text → List[SentenceScore]
#   Stage 2:   EntityRecognizer     — NER → result.entities_in_article
#   Stage 3:   SentenceExtraction   — BertSum + NLI dedup
#   Stage 4:   Decontextualizer     — QA-based rewrite to self-contained sentences
#   Stage 5:   CheckWorthiness      — claim-worthy classification
#   Stage 5.5: EntityMapping        — link article entities → individual sentences
#   Stage 6:   Embedder             — dense vector embeddings
#   Stage 7:   Sentence→Claim       — commit claims to result
#   Stage 8:   BiasDetector         — article-level bias profile (optional)
PIPELINE_ORDER = [
    ("ClaimExtraction", ClaimExtraction, "ArticleProcessor"),
]


def _dummy_embedding(dim: int = EMBEDDING_DIM) -> List[float]:
    return [random.uniform(-0.2, 0.2) for _ in range(dim)]


def _build_dummy_result() -> NLPResult:
    # Generate claims similar to the 3 dummy seed articles
    dummy_claims = [
        "Government raised taxes",
        "Tax increases were approved",
        "New tax hike announced",
    ]

    entities = [
        Entity(entity_text="Government", type_of_entity="ORG", start_char=0, end_char=10),
        Entity(entity_text="taxes", type_of_entity="TOPIC", start_char=11, end_char=16),
    ]

    # Randomly select one of the dummy claims
    claim_text = random.choice(dummy_claims)

    claim = Claim(
        confidence=0.9,
        source_sentence_indices=[0],
        decontextualised_claim_text=claim_text,
        decontextualised_claim_embedding=_dummy_embedding(),
        NER_entities=entities,
    )
    bias_profile = BiasProfile(
        bias_category="center",
        bias_analysis_confidence=0.7,
        sentiment_category="neutral",
        sentiment_analysis_confidence=0.8,
    )

    result = NLPResult()
    result.claims_in_article = [claim]
    result.entities_in_article = entities
    result.bias_profile = bias_profile
    return result


class NLPService(ServiceTemplate):

    def __init__(self, config: ServiceConfig, options: NLPOptions) -> None:
        super().__init__(config)

        if torch.cuda.is_available():
            self.logger.info("GPU DETECTED")
        else:
            self.logger.info("GPU NOT DETECTED")

        self.options = options or NLPOptions(
            enable_decontextualization=ENABLE_DECONTEXTUALIZATION
        )
        # Only load models if NOT in dummy mode
        if DUMMY_NLP_MODE:
            logger.info("DUMMY_NLP_MODE enabled - skipping model loading")
            self.pipeline = []
        else:
            # Load all registered models via ModelManager before component init.
            # Sequential on GPU, parallel on CPU.
            model_manager.load_all()

            # Flat component pipeline — each component is instantiated independently
            # and dispatched via typed tags (SentenceGenerator, SentenceProcessor,
            # SentenceConsumer, ArticleProcessor).
            self.pipeline = [
                (name, cls(device_config=DEVICE_CONFIG, model_manager=model_manager), ctype)
                for name, cls, ctype in PIPELINE_ORDER
            ]
            logger.info("Model health: %s", model_manager.health_check())
        
        self.stats_json_handler = JsonHandler(filename="stats.json")
        
    def _log_stats(self,
               news_outlet: str,
               len_claims_extracted: int,
               entities_extracted: List[Entity],
               bias_profile: BiasProfile,
               error_type: Optional[str] = None) -> None:

        data = self.stats_json_handler.read_json()
        day_key = datetime.now().date().isoformat()

        entry = data.setdefault(day_key, {
            "jobs_processed": 0,
            "claims_extracted": 0,
            "entities_extracted": 0,
            "bias_profiles": {
                "left": 0, "right": 0, "center": 0,
                "subjective": 0, "objective": 0,
                "emotive": 0, "non_emotive": 0
            },
            "entity_distribution": {},
            "outlet_stats": {},
            "errors": {}
        })
        
        # Update global totals
        entry["jobs_processed"] += 1
        entry["claims_extracted"] += len_claims_extracted
        entry["entities_extracted"] += len(entities_extracted)

        # Update global entity distribution
        for ent in entities_extracted:
            entry["entity_distribution"][ent.type_of_entity] = (
                entry["entity_distribution"].get(ent.type_of_entity, 0) + 1
            )

        # Update global bias profile counts
        if bias_profile:
            if bias_profile.bias_category.lower() not in entry["bias_profiles"]:
                entry["bias_profiles"][bias_profile.bias_category.lower()] =1
            entry["bias_profiles"][bias_profile.bias_category.lower()] += 1
            entry["bias_profiles"][bias_profile.sentiment_category.lower()] += 1

        # Errors
        if error_type:
            entry["errors"][error_type] = entry["errors"].get(error_type, 0) + 1

        # --- Outlet‑level stats ---
        outlet_entry = entry["outlet_stats"].setdefault(news_outlet, {
            "jobs_processed": 0,
            "claims_extracted": 0,
            "entities_extracted": 0,
            "entity_distribution": {},
            "bias_profiles": {
                "left": 0, "right": 0, "center": 0,
                "subjective": 0, "objective": 0,
                "emotive": 0, "non_emotive": 0
            },
            "errors": {}
        })

        outlet_entry["jobs"] += 1
        outlet_entry["claims_extracted"] += len_claims_extracted
        outlet_entry["entities_extracted"] += len(entities_extracted)

        # Outlet entity distribution
        for ent in entities_extracted:
            outlet_entry["entity_distribution"][ent.type_of_entity] = (
                outlet_entry["entity_distribution"].get(ent.type_of_entity, 0) + 1
            )

        # Outlet bias profiles
        if bias_profile:
            if bias_profile.bias_category.lower() not in outlet_entry["bias_profiles"]:
                outlet_entry["bias_profiles"][bias_profile.bias_category.lower()] =1
            outlet_entry["bias_profiles"][bias_profile.bias_category] += 1
            outlet_entry["bias_profiles"][bias_profile.sentiment_category] += 1

        # Outlet errors
        if error_type:
            outlet_entry["errors"][error_type] = outlet_entry["errors"].get(error_type, 0) + 1

        # Prune to last 30 days
        MAX_DAYS = 30
        dates = sorted(data.keys())
        if len(dates) > MAX_DAYS:
            for old_date in dates[:-MAX_DAYS]:
                del data[old_date]

        self.stats_json_handler.write_json(data)


    def _analyze_html_and_update(self, message: StreamMessage) -> StreamMessage:
        """
        Runs the article through each pipeline component using typed dispatch.

        Dispatch types (matching the test scripts):
          SentenceGenerator  — run(article, message, options) -> List[SentenceScore]
          SentenceProcessor  — run(article, message, options, sentences) -> List[SentenceScore]
          SentenceConsumer   — run(article, message, options, sentences) -> None
          ArticleProcessor   — run(article, message, options) -> None
        """
        article = Article(text=message.text, title=message.title, link=message.link)
        sentences: List[SentenceScore] = []

        for name, component, component_type in self.pipeline:
            try:
                if component_type == "SentenceGenerator":
                    sentences = component.run(article, message, self.options)
                elif component_type == "SentenceProcessor":
                    sentences = component.run(
                        article, message, self.options, sentences
                    )
                elif component_type == "SentenceConsumer":
                    component.run(article, message, self.options, sentences)
                else:  # ArticleProcessor
                    component.run(article, message, self.options)
            except torch.cuda.OutOfMemoryError as oom:
                logger.error(
                    "CUDA OOM in %s: %s. Flushing cache and aborting article.",
                    name,
                    oom,
                )
                torch.cuda.empty_cache()
                raise
            except Exception as e:
                logger.error("Pipeline error in %s: %s", name, e)
                raise

        # Expose processed sentences for downstream services.
        # ClaimExtraction sets result.sentences internally; only override
        # if the dispatch loop produced its own sentence list.

        # if sentences:
        #     result = message.create_nlp_result()
        #     result.sentences = sentences
        #     message.set_nlp_result(result)
        
        validate_after_nlp(stream_message=message, message=None)
        self.logger.debug(get_pretty_print_stream_message(message))
        return message

    def _process_message(self, message: StreamMessage) -> StreamMessage:
        try:
            if DUMMY_NLP_MODE:
                dummy_result = _build_dummy_result()
                message.set_nlp_result(dummy_result)
                return message

            self._analyze_html_and_update(message)
            
            
            
            self._log_stats(
                news_outlet=message.data.payload.news_outlet,
                len_claims_extracted=len(message.all_claims),
                entities_extracted=message.all_entities,
                bias_profile=message.bias_profile
            )
            
            return message
        except Exception as e:
            self._log_stats(
                news_outlet=message.data.payload.news_outlet,
                len_claims_extracted=len(message.all_claims),
                entities_extracted=message.all_entities,
                bias_profile=message.bias_profile
            )
            raise ProcessingError(f"Failed to analyze {message.link}: {e}")
        finally:
            # Always flush the GPU cache after a message to prevent OOM accumulation
            # across articles on long-running stream consumers.
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
