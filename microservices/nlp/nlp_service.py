# microservices/nlp/nlp_service.py
from typing import List
from logging import getLogger
import random

from common.models.api.redis_models import (
    Article,
    BiasProfile,
    Claim,
    Entity,
    NLPOptions,
    NLPResult,
    StreamMessage,
)
from common.service.service_template import ProcessingError, ServiceConfig, ServiceTemplate

from microservices.nlp.models.base import NLPComponent

# We will implement these empty skeletons in the next step
from microservices.nlp.components.preprocess import Preprocessor
from microservices.nlp.components.centrality import CentralityScorer
from microservices.nlp.components.embedder import Embedder
from microservices.nlp.components.bias import BiasDetector
from microservices.nlp.components.ner import EntityRecognizer
from microservices.nlp.components.checkworthy import CheckWorthinessFilter
from microservices.nlp.config import DUMMY_NLP_MODE

logger = getLogger("NLP")
EMBEDDING_DIM = 768


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
        contextualised_claim_text=claim_text,
        decontextualised_claim_text=claim_text,
        decontextualised_claim_embedding=_dummy_embedding(),
        NER_entities=entities,
    )
    bias_profile = BiasProfile(
        political_bias="center",
        confidence=0.7,
        scores={"left": 0.2, "center": 0.7, "right": 0.1},
        emotional_tone="neutral",
    )

    result = NLPResult()
    result.claims_in_article = [claim]
    result.entities_in_article = entities
    result.bias_profile = bias_profile
    return result

class NLPService(ServiceTemplate):

    def __init__(self, config:ServiceConfig, options: NLPOptions) -> None:
        super().__init__(config)
        
        self.options = options or NLPOptions()        
        
        # Only load models if NOT in dummy mode
        if DUMMY_NLP_MODE:
            logger.info("DUMMY_NLP_MODE enabled - skipping model loading")
            self.pipeline: List[NLPComponent] = []
        else:
            # Define the execution order of the pipeline
            self.pipeline: List[NLPComponent] = [
                Preprocessor(),
                Embedder(),
                CentralityScorer(),
                BiasDetector(),
                EntityRecognizer(),
                CheckWorthinessFilter()
            ]
    
    
    def _analyze_html_and_update(self, message: StreamMessage) -> StreamMessage:
        """
        The main orchestrator that passes the article through each pipeline stage.
        """
        article = Article(text=message.text, title=message.title, link=message.link)
        analysis_result = NLPResult()

        for component in self.pipeline:
            try:
                component.run(article, analysis_result, self.options)                
            except Exception as e:
                print(f"Pipeline error in {component.__class__.__name__}: {str(e)}")
                raise
            
        message.set_nlp_result(analysis_result)
        return message


    def _process_message(self, message: StreamMessage) -> StreamMessage:
        try:
            if message.data.header.type == "user":
                logger.info("Received user message for NLP: %s", message.data.payload)

            if DUMMY_NLP_MODE:
                dummy_result = _build_dummy_result()
                message.set_nlp_result(dummy_result)
                return message

            analyzed_message:StreamMessage = self._analyze_html_and_update(message)
            return analyzed_message
        except Exception as e:
            raise ProcessingError(f"Failed to analyze {message.link}: {e}")
        
 