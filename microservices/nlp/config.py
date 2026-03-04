from typing import List
from dotenv import load_dotenv
from common.env.log_env import print_env, Config, EnvVariable
from common.env.get_env_var import get_env_var
from logging import Logger, getLogger

load_dotenv()
config_logger: Logger = getLogger("config")

# =============================================================================
# PIPELINE CONSTANTS
# Safe to import from any context (tests, components, service).
# Tweak values here without touching component code.
# =============================================================================

# ── Model Names ───────────────────────────────────────────────────────────────
# Primary models — can also be overridden via environment variables (see service
# config section below).  These defaults match what the pipeline was built with.
NER_MODEL             = "dslim/bert-base-NER-uncased"
EMBEDDING_MODEL       = "sentence-transformers/all-mpnet-base-v2"
BERT_SCORING_MODEL    = "bert-base-uncased"
NLI_MODEL             = "cross-encoder/nli-distilroberta-base"
QG_MODEL              = "mrm8488/t5-base-finetuned-question-generation-ap"
QA_MODEL              = "deepset/roberta-base-squad2"
GEN_MODEL             = "google/flan-t5-base"
BIAS_POLITICAL_MODEL  = "typeform/distilbert-base-uncased-mnli"
BIAS_SENTIMENT_MODEL  = "cardiffnlp/twitter-roberta-base-sentiment-latest"
CW_NLI_MODEL          = "typeform/distilbert-base-uncased-mnli"  # Zero-shot claim classifier (shared with BiasDetector)

# ── Thresholds ────────────────────────────────────────────────────────────────
# Minimum confidence for a check-worthy sentence to be promoted to a Claim.
# Lowered from 0.75: the hybrid CW ensemble (NLI + heuristic) tops out ~0.65
# on strong factual sentences; 0.50 preserves discrimination without blocking all claims.
CLAIM_MIN_CONFIDENCE     = 0.50
# Minimum check-worthiness score for a sentence to be flagged is_checkworthy.
# Intentionally lower than CLAIM_MIN_CONFIDENCE: CW is a broad net,
# CLAIM_MIN_CONFIDENCE is the final promotion gate in Stage 7.
CW_THRESHOLD             = 0.45   # Lowered: the NLI zero-shot model pulls ensemble scores down
# Ensemble weights for hybrid CW scorer (NLI transformer vs. spaCy heuristic)
# NOTE: typeform/distilbert-base-uncased-mnli zero-shot gives 0.30–0.50 for
# "verifiable factual claim" even on strong sentences — it is not calibrated
# for this label. The heuristic is the better-calibrated primary signal.
CW_NLI_WEIGHT            = 0.40   # NLI provides soft signal, not primary driver
CW_HEURISTIC_WEIGHT      = 0.60   # spaCy heuristic is primary (SVO + NER + hedging)
# NLI entailment probability above which a candidate sentence is considered
# redundant with an already-selected one (Stage 3 deduplication).
NLI_ENTAILMENT_THRESHOLD = 0.70
# QA answers below this confidence are discarded in decontextualisation.
QA_SCORE_THRESHOLD       = 0.35

# ── Batch / Sequence Limits ───────────────────────────────────────────────────
NER_BATCH_SIZE           = 16   # NER pipeline batch size
CW_BATCH_SIZE            = 32   # CheckWorthiness spaCy pipe batch size
EMBEDDER_BATCH_SIZE      = 32   # Sentence embedding batch size
SENTENCE_SCORING_BATCH   = 16   # BertSum CLS scoring batch size
NLI_MAX_PAIRS            = 32   # Max NLI pairs checked per deduplication pass
DECONTEXT_QG_BATCH_SIZE  = 16   # QG (t5-base, short prompts) — increase freely on GPU
DECONTEXT_QA_BATCH_SIZE  = 16   # QA (roberta-base-squad2) — contexts can be long, 16 is safe
DECONTEXT_GEN_BATCH_SIZE = 16   # QA2D / final rewrite (flan-t5-base) — longer prompts, keep at 16
BM25_TOP_K               = 3    # Evidence sentences retrieved per BM25 query
BERT_MAX_LENGTH          = 512  # Tokenizer truncation for BERT-class models
DECONTEXT_MAX_GEN_LENGTH = 128  # Max output tokens for decontextualisation rewrites
DECONTEXT_MAX_UNITS      = 6    # Max ambiguous units resolved per sentence
DECONTEXT_REWRITE_RATIO  = 4  # Reject rewrites longer than N× the original
BIAS_MAX_CHARS           = 2000 # Article characters fed to bias classifier
BIAS_SENTIMENT_MAX_LEN   = 128  # Sentiment pipeline token truncation

# ── Preprocessing Filters ─────────────────────────────────────────────────────
PREPROCESS_MIN_TOKENS    = 7    # Sentences shorter than this are dropped
PHOTO_CREDIT_MAX_LEN     = 120  # Photo-credit lines are at most this many chars

# ── Extraction ────────────────────────────────────────────────────────────────
SENTENCE_EXTRACT_TOP_K   = 10   # Default max sentences kept after extraction

# =============================================================================
# SERVICE CONFIG  (requires environment variables — only used by main.py)
# Components import only from the block above; this block is wrapped so that
# component-only imports (e.g. in tests) do not call exit(1) on missing vars.
# =============================================================================
try:
    INPUT_STREAMS: List[str] = get_env_var("INPUT_STREAMS", str, config_logger).split(", ")
    USER_OUTPUT_STREAM: str = get_env_var("USER_OUTPUT_STREAM", str, config_logger)
    BACKGROUND_OUTPUT_STREAM: str = get_env_var("BACKGROUND_OUTPUT_STREAM", str, config_logger)
    FAILURE_OUTPUT_STREAM: str = get_env_var("FAILURE_OUTPUT_STREAM", str, config_logger)

    GROUP_NAME: str = get_env_var("GROUP_NAME", str, config_logger)
    CONSUMER_NAME: str = get_env_var("CONSUMER_NAME", str, config_logger)
    NLP_MAX_WORKERS: int = get_env_var("NLP_MAX_WORKERS", str, config_logger)
    BATCH_SIZE: int = get_env_var("BATCH_SIZE", int, config_logger)

    DUMMY_NLP_MODE: bool = get_env_var(
        "DUMMY_NLP_MODE",
        lambda x: str(x).lower() in {"1", "true", "yes", "y"},
        config_logger,
        default=False,
    )

    # Allow model overrides via env without touching code
    NER_MODEL       = get_env_var("NLP_NER_MODEL",       str, config_logger, NER_MODEL)
    EMBEDDING_MODEL = get_env_var("NLP_EMBEDDING_MODEL", str, config_logger, EMBEDDING_MODEL)
    BIAS_POLITICAL_MODEL = get_env_var("NLP_BIAS_MODEL", str, config_logger, BIAS_POLITICAL_MODEL)
    DEVICE = "cuda" if get_env_var("USE_GPU", str, config_logger, "false").lower() == "true" else "cpu"

    input_streams: List[str] = INPUT_STREAMS
    output_streams: List[str] = [USER_OUTPUT_STREAM, BACKGROUND_OUTPUT_STREAM, FAILURE_OUTPUT_STREAM]

    env_variables: List[EnvVariable] = [
        EnvVariable("INPUT_STREAMS",            INPUT_STREAMS),
        EnvVariable("USER_OUTPUT_STREAM",       USER_OUTPUT_STREAM),
        EnvVariable("BACKGROUND_OUTPUT_STREAM", BACKGROUND_OUTPUT_STREAM),
        EnvVariable("FAILURE_OUTPUT_STREAM",    FAILURE_OUTPUT_STREAM),
        EnvVariable("GROUP_NAME",               GROUP_NAME),
        EnvVariable("CONSUMER_NAME",            CONSUMER_NAME),
        EnvVariable("NLP_MAX_WORKERS",          NLP_MAX_WORKERS),
        EnvVariable("BATCH_SIZE",               BATCH_SIZE),
        EnvVariable("NER_MODEL",                NER_MODEL),
        EnvVariable("EMBEDDING_MODEL",          EMBEDDING_MODEL),
        EnvVariable("BIAS_POLITICAL_MODEL",     BIAS_POLITICAL_MODEL),
        EnvVariable("CLAIM_MIN_CONFIDENCE",     CLAIM_MIN_CONFIDENCE),
        EnvVariable("CW_THRESHOLD",             CW_THRESHOLD),
        EnvVariable("DUMMY_NLP_MODE",           DUMMY_NLP_MODE),
    ]

    print_env(Config(env_variables, input_streams, output_streams), config_logger)

except SystemExit:
    # Service env vars not available — running in component/test context.
    # Pipeline constants above are still fully usable.
    DUMMY_NLP_MODE = False
    # Fallback device detection for non-service context
    if torch.backends.mps.is_available():
        DEVICE = "mps"
    elif torch.cuda.is_available():
        DEVICE = "cuda"
    else:
        DEVICE = "cpu"
