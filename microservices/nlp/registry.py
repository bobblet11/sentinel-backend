# microservices/nlp/registry.py
import logging
from typing import Any
from sentence_transformers import SentenceTransformer
from transformers import pipeline
from microservices.nlp.config import NLPConfig

# Setup basic logging
logger = logging.getLogger("nlp_service.registry")

class ModelRegistry:
    """
    Singleton-style registry to manage heavy ML models.
    Ensures models are loaded only once and reused.
    """
    
    # Class-level storage for loaded models
    _embedder: Any = None
    _ner_pipeline: Any = None
    _bias_classifier: Any = None

    @classmethod
    def get_embedder(cls):
        """Returns the SentenceTransformer model."""
        if cls._embedder is None:
            logger.info(f"Loading Embedder: {NLPConfig.EMBEDDING_MODEL}...")
            # This aligns with the SentenceEmbedder interface (has .encode method)
            cls._embedder = SentenceTransformer(NLPConfig.EMBEDDING_MODEL, device=NLPConfig.DEVICE)
            logger.info("Embedder loaded.")
        return cls._embedder

    @classmethod
    def get_ner_pipeline(cls):
        """Returns the HuggingFace NER pipeline."""
        if cls._ner_pipeline is None:
            logger.info(f"Loading NER model: {NLPConfig.NER_MODEL}...")
            cls._ner_pipeline = pipeline(
                "ner", 
                model=NLPConfig.NER_MODEL, 
                aggregation_strategy="simple",
                device=0 if NLPConfig.DEVICE == "cuda" else -1
            )
            logger.info("NER pipeline loaded.")
        return cls._ner_pipeline

    @classmethod
    def get_bias_classifier(cls):
        """Returns the Zero-Shot Classification pipeline for bias detection."""
        if cls._bias_classifier is None:
            logger.info(f"Loading Bias model: {NLPConfig.BIAS_MODEL}...")
            cls._bias_classifier = pipeline(
                "zero-shot-classification", 
                model=NLPConfig.BIAS_MODEL,
                device=0 if NLPConfig.DEVICE == "cuda" else -1
            )
            logger.info("Bias classifier loaded.")
        return cls._bias_classifier

    @classmethod
    def warmup(cls):
        """
        Forces all models to load into memory.
        Call this during service startup (e.g. in __init__ or before accepting traffic).
        """
        logger.info("Starting model warmup...")
        cls.get_embedder()
        cls.get_ner_pipeline()
        cls.get_bias_classifier()
        logger.info("Model warmup complete.")