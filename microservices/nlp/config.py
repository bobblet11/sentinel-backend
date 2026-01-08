"""
Configuration constants for the Sentinel NLP service.
"""

# Default thresholds
DEFAULT_TOP_K: int = 5
DEFAULT_CONFIDENCE_THRESHOLD: float = 0.5
DEFAULT_MAX_CLAIMS: int = 10

# Feature toggles
ENABLE_BIAS: bool = False
ENABLE_NER: bool = True
ENABLE_DECONTEXTUALIZATION: bool = True

# Centrality settings
CENTRALITY_PREFILTER_TOP_K: int = 20

# Model settings
EMBEDDING_MODEL_NAME: str = "sentence-transformers/all-MiniLM-L6-v2"
BIAS_MODEL_NAME: str = "d4data/bias-detection-model"
NER_MODEL_NAME: str = "dslim/bert-base-NER"

# Label sets
BIAS_LABELS: list[str] = ["Left", "Center", "Right"]
ENTITY_LABELS: list[str] = ["PER", "ORG", "LOC", "MISC"]
