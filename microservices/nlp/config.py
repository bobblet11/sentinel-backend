# microservices/nlp/config.py
import os

class NLPConfig:
    """Central configuration for model names and paths."""
    
    # Embedding Model: optimized for semantic search (384 dimensions)
    # Matches the 'vector(384)' requirement for pgvector
    EMBEDDING_MODEL = os.getenv("NLP_EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    
    # NER Model: Standard BERT-based NER
    NER_MODEL = os.getenv("NLP_NER_MODEL", "dslim/bert-base-NER")
    
    # Bias/Zero-Shot Model: For political leaning and tone
    # 'facebook/bart-large-mnli' is great for zero-shot classification
    BIAS_MODEL = os.getenv("NLP_BIAS_MODEL", "facebook/bart-large-mnli")
    
    # Device selection (cuda if available, else cpu)
    DEVICE = "cuda" if os.getenv("USE_GPU", "false").lower() == "true" else "cpu"