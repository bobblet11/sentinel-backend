from logging import Logger, getLogger
from typing import List

from dotenv import load_dotenv

from common.env.get_env_var import get_env_var
from common.env.log_env import Config, EnvVariable, print_env

load_dotenv()
config_logger: Logger = getLogger("config")

# =============================================================================
# PIPELINE CONSTANTS
# Safe to import from any context (tests, components, service).
# Tweak values here without touching component code.
# =============================================================================

# ── Model Names ───────────────────────────────────────────────────────────────
NER_MODEL = "dslim/bert-base-NER-uncased"
EMBEDDING_MODEL = "sentence-transformers/all-mpnet-base-v2"
BERT_SCORING_MODEL = "bert-base-uncased"
NLI_MODEL = "cross-encoder/nli-distilroberta-base"
QG_MODEL = "Salesforce/mixqg-base"
QA_MODEL = "deepset/roberta-base-squad2"
GEN_MODEL = "google/flan-t5-base"
BIAS_POLITICAL_MODEL = "premsa/political-bias-prediction-allsides-BERT"
BIAS_SENTIMENT_MODEL = "cardiffnlp/twitter-roberta-base-sentiment-latest"
CW_NLI_MODEL = "typeform/distilbert-base-uncased-mnli"

# ── Thresholds ────────────────────────────────────────────────────────────────
CLAIM_MIN_CONFIDENCE = 0.50
CW_THRESHOLD = 0.45
CW_NLI_WEIGHT = 0.40
CW_HEURISTIC_WEIGHT = 0.60
NLI_ENTAILMENT_THRESHOLD = 0.70
QA_SCORE_THRESHOLD = 0.20
TOPIC_SIMILARITY_THRESHOLD: float = 0.15

# ── Topic Classification ──────────────────────────────────────────────────────
TOPIC_LABELS: List[str] = [
    "Politics",
    "World",
    "Technology",
    "Health",
    "Science",
    "Business",
    "Entertainment",
    "Sports",
    "General",
]

# ── CheckWorthiness (kept for backward compatibility with CheckWorthinessFilter)
CHECKWORTHY_MODEL = "whispAI/ClaimBuster-DeBERTaV2"
CHECKWORTHY_BATCH_SIZE = 16
MAX_SENTENCES_FOR_CHECKWORTHY = 40

# ── Batch / Sequence Limits ───────────────────────────────────────────────────
NER_BATCH_SIZE = 16
CW_BATCH_SIZE = 32
EMBEDDER_BATCH_SIZE = 32
SENTENCE_SCORING_BATCH = 16
NLI_MAX_PAIRS = 32
DECONTEXT_QG_BATCH_SIZE = 16
DECONTEXT_QA_BATCH_SIZE = 16
DECONTEXT_GEN_BATCH_SIZE = 16
BM25_TOP_K = 3
BERT_MAX_LENGTH = 512
DECONTEXT_MAX_GEN_LENGTH = 128
DECONTEXT_MAX_UNITS = 6
DECONTEXT_REWRITE_RATIO = 4
BIAS_MAX_CHARS = 2000
BIAS_SENTIMENT_MAX_LEN = 128

# Kept for backward compatibility with existing ModelManager registrations
BIAS_MAX_ARTICLE_TEXT_CHARS: int = BIAS_MAX_CHARS
BIAS_MAX_SENTENCES_TO_CLASSIFY: int = 0
BIAS_MAX_SENTENCE_TEXT_CHARS: int = 220

# ── Preprocessing Filters ─────────────────────────────────────────────────────
PREPROCESS_MIN_TOKENS = 7
PHOTO_CREDIT_MAX_LEN = 120

# ── Extraction ────────────────────────────────────────────────────────────────
SENTENCE_EXTRACT_TOP_K = 15

# =============================================================================
# SERVICE CONFIG  (requires environment variables — only used by main.py)
# Components import only from the block above; this block is wrapped so that
# component-only imports (e.g. in tests) do not call exit(1) on missing vars.
# =============================================================================
try:
    LOG_MODE: int = get_env_var("LOG_MODE", int, config_logger)

    INPUT_STREAMS: List[str] = [
        x.strip(" ,")
        for x in get_env_var("INPUT_STREAMS", str, config_logger).split(",")
    ]
    USER_OUTPUT_STREAM: str = get_env_var("USER_OUTPUT_STREAM", str, config_logger)
    BACKGROUND_OUTPUT_STREAM: str = get_env_var(
        "BACKGROUND_OUTPUT_STREAM", str, config_logger
    )
    FAILURE_OUTPUT_STREAM: str = get_env_var(
        "FAILURE_OUTPUT_STREAM", str, config_logger
    )

    GROUP_NAME: str = get_env_var("GROUP_NAME", str, config_logger)
    CONSUMER_NAME: str = get_env_var("CONSUMER_NAME", str, config_logger)
    NLP_MAX_WORKERS: int = get_env_var("NLP_MAX_WORKERS", int, config_logger)
    BATCH_SIZE: int = get_env_var("BATCH_SIZE", int, config_logger)

    DUMMY_NLP_MODE: bool = get_env_var(
        "DUMMY_NLP_MODE",
        lambda x: str(x).lower() in {"1", "true", "yes", "y"},
        config_logger,
        default=False,
    )
    ENABLE_DECONTEXTUALIZATION: bool = get_env_var(
        "ENABLE_DECONTEXTUALIZATION",
        lambda x: str(x).lower() in {"1", "true", "yes", "y"},
        config_logger,
        default=True,
    )

    # Allow model overrides via env without touching code
    NER_MODEL = get_env_var("NLP_NER_MODEL", str, config_logger, NER_MODEL)
    EMBEDDING_MODEL = get_env_var(
        "NLP_EMBEDDING_MODEL", str, config_logger, EMBEDDING_MODEL
    )
    BIAS_POLITICAL_MODEL = get_env_var(
        "NLP_BIAS_MODEL", str, config_logger, BIAS_POLITICAL_MODEL
    )
    BIAS_SENTIMENT_MODEL = get_env_var(
        "NLP_SENTIMENT_MODEL", str, config_logger, BIAS_SENTIMENT_MODEL
    )
    QG_MODEL = get_env_var("NLP_QG_MODEL", str, config_logger, QG_MODEL)
    QA_MODEL = get_env_var("NLP_QA_MODEL", str, config_logger, QA_MODEL)
    GEN_MODEL = get_env_var("NLP_GEN_MODEL", str, config_logger, GEN_MODEL)
    TOPIC_SIMILARITY_THRESHOLD = get_env_var(
        "NLP_TOPIC_SIMILARITY_THRESHOLD",
        float,
        config_logger,
        TOPIC_SIMILARITY_THRESHOLD,
    )

    # Unified device config for all NLP components
    use_gpu = get_env_var("USE_GPU", str, config_logger, "false").lower() == "true"

    from microservices.nlp.components.device import DeviceConfig

    DEVICE_CONFIG = DeviceConfig.resolve(use_gpu=use_gpu)
    DEVICE = DEVICE_CONFIG.device  # backward compat alias for ModelManager

    input_streams: List[str] = INPUT_STREAMS
    output_streams: List[str] = [
        USER_OUTPUT_STREAM,
        BACKGROUND_OUTPUT_STREAM,
        FAILURE_OUTPUT_STREAM,
    ]

    env_variables: List[EnvVariable] = [
        EnvVariable("LOG_MODE", LOG_MODE),
        EnvVariable("INPUT_STREAMS", INPUT_STREAMS),
        EnvVariable("USER_OUTPUT_STREAM", USER_OUTPUT_STREAM),
        EnvVariable("BACKGROUND_OUTPUT_STREAM", BACKGROUND_OUTPUT_STREAM),
        EnvVariable("FAILURE_OUTPUT_STREAM", FAILURE_OUTPUT_STREAM),
        EnvVariable("GROUP_NAME", GROUP_NAME),
        EnvVariable("CONSUMER_NAME", CONSUMER_NAME),
        EnvVariable("NLP_MAX_WORKERS", NLP_MAX_WORKERS),
        EnvVariable("BATCH_SIZE", BATCH_SIZE),
        EnvVariable("NER_MODEL", NER_MODEL),
        EnvVariable("EMBEDDING_MODEL", EMBEDDING_MODEL),
        EnvVariable("BIAS_POLITICAL_MODEL", BIAS_POLITICAL_MODEL),
        EnvVariable("BIAS_SENTIMENT_MODEL", BIAS_SENTIMENT_MODEL),
        EnvVariable("QG_MODEL", QG_MODEL),
        EnvVariable("QA_MODEL", QA_MODEL),
        EnvVariable("GEN_MODEL", GEN_MODEL),
        EnvVariable("CLAIM_MIN_CONFIDENCE", CLAIM_MIN_CONFIDENCE),
        EnvVariable("CW_THRESHOLD", CW_THRESHOLD),
        EnvVariable("DUMMY_NLP_MODE", DUMMY_NLP_MODE),
        EnvVariable("ENABLE_DECONTEXTUALIZATION", ENABLE_DECONTEXTUALIZATION),
    ]

    print_env(Config(env_variables, input_streams, output_streams), config_logger)

except SystemExit:
    # Service env vars not available — running in component/test context.
    # Pipeline constants above are still fully usable.
    DUMMY_NLP_MODE = False

    import os

    from microservices.nlp.components.device import DeviceConfig

    ENABLE_DECONTEXTUALIZATION = os.environ.get(
        "ENABLE_DECONTEXTUALIZATION", "true"
    ).lower() in {"1", "true", "yes", "y"}
    _use_gpu_fallback = os.environ.get("USE_GPU", "false").lower() == "true"
    DEVICE_CONFIG = DeviceConfig.resolve(use_gpu=_use_gpu_fallback)
    DEVICE = DEVICE_CONFIG.device

from common.model_manager.manager import ModelManager

# Centralized model manager instance — models are registered but not yet loaded
model_manager = ModelManager(device=DEVICE, dummy_mode=DUMMY_NLP_MODE)
model_manager.register_defaults()
