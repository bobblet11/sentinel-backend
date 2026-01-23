import os
import logging
import torch
from transformers import (
    AutoTokenizer, 
    AutoModelForSequenceClassification, 
    AutoModelForTokenClassification, 
    pipeline
)
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

# Load env vars
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ModelRegistry:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ModelRegistry, cls).__new__(cls)
            cls._instance.initialized = False
        return cls._instance

    def __init__(self):
        if self.initialized:
            return
            
        self.device = os.getenv("INFERENCE_DEVICE", "cpu")
        logger.info(f"Registry initialized. Target device: {self.device}")
        
        # Model placeholders
        self._ner_pipeline = None
        self._bias_model = None
        self._bias_tokenizer = None
        self._embedding_model = None
        
        self.initialized = True

    @property
    def ner(self):
        """Lazy loads the Named Entity Recognition pipeline"""
        if self._ner_pipeline is None:
            model_name = os.getenv("MODEL_NER", "dslim/bert-base-ner")
            logger.info(f"Loading NER model: {model_name}...")
            
            # aggregation_strategy="simple" groups sub-tokens into whole words
            self._ner_pipeline = pipeline(
                "ner", 
                model=model_name, 
                tokenizer=model_name, 
                device=0 if self.device == "cuda" else -1,
                aggregation_strategy="simple"
            )
            logger.info("NER model loaded.")
        return self._ner_pipeline

    @property
    def bias(self):
        """Lazy loads the Bias Detection model & tokenizer"""
        if self._bias_model is None:
            model_name = os.getenv("MODEL_BIAS", "valurank/distilroberta-bias")
            logger.info(f"Loading Bias model: {model_name}...")
            
            self._bias_tokenizer = AutoTokenizer.from_pretrained(model_name)
            self._bias_model = AutoModelForSequenceClassification.from_pretrained(model_name)
            
            if self.device == "cuda":
                self._bias_model.cuda()
            elif self.device == "mps":
                self._bias_model.to("mps")
                
            logger.info("Bias model loaded.")
            
        return (self._bias_model, self._bias_tokenizer)

    @property
    def embeddings(self):
        """Lazy loads the Sentence Transformer model for embeddings"""
        if self._embedding_model is None:
            model_name = os.getenv("MODEL_EMBEDDINGS", "sentence-transformers/all-MiniLM-L6-v2")
            logger.info(f"Loading Embedding model: {model_name}...")
            
            self._embedding_model = SentenceTransformer(model_name, device=self.device)
            logger.info("Embedding model loaded.")
        return self._embedding_model

# Global instance
registry = ModelRegistry()