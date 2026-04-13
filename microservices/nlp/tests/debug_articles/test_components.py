"""
Test each NLP pipeline component individually with selective model loading.

Usage (from /app inside the NLP container, or from workspace root locally):
    python microservices/nlp/tests/debug_articles/test_components.py <path/to/article.json> [--component COMPONENT]

Examples:
    python microservices/nlp/tests/debug_articles/test_components.py microservices/nlp/tests/debug_articles/bbc_001.json
    python microservices/nlp/tests/debug_articles/test_components.py microservices/nlp/tests/debug_articles/bbc_001.json --component preprocessor
    python microservices/nlp/tests/debug_articles/test_components.py microservices/nlp/tests/debug_articles/bbc_001.json --component ner
    python microservices/nlp/tests/debug_articles/test_components.py microservices/nlp/tests/debug_articles/bbc_001.json --component bias

Components: preprocessor, embedder, centrality, ner, bias, checkworthy, all (default)
"""

import argparse
import json
import logging
import os
import sys
import time
import traceback
import uuid
from pathlib import Path

import numpy as np

# ---------------------------------------------------------------------------
# Path setup — must happen before any project imports
# ---------------------------------------------------------------------------
WORKSPACE_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(WORKSPACE_ROOT))

# ---------------------------------------------------------------------------
# Argument parsing (pre-import so we can set env vars before loading config)
# ---------------------------------------------------------------------------
parser = argparse.ArgumentParser(
    description="Test individual NLP pipeline components on a single article JSON."
)
parser.add_argument("article_json", help="Path to the article JSON file to analyse")
parser.add_argument(
    "--component",
    default="all",
    choices=[
        "preprocessor",
        "embedder",
        "centrality",
        "ner",
        "bias",
        "checkworthy",
        "all",
    ],
    help="Which component to test (default: all)",
)
parser.add_argument(
    "--debug",
    action="store_true",
    help="Enable DEBUG logging to see component internals (default: INFO)",
)
args = parser.parse_args()

# ---------------------------------------------------------------------------
# Environment variable setup (copied from run_pipeline_tests.py lines 44-74)
# ---------------------------------------------------------------------------
os.environ.setdefault("DUMMY_NLP_MODE", "false")

_NLP_TEST_CACHE = (
    WORKSPACE_ROOT / "microservices" / "nlp" / "tests" / ".cache" / "huggingface"
)
os.environ.setdefault("HF_HOME", str(_NLP_TEST_CACHE))
os.environ.setdefault("TRANSFORMERS_CACHE", str(_NLP_TEST_CACHE / "hub"))

os.environ["NLP_EMBEDDING_MODEL"] = "sentence-transformers/all-mpnet-base-v2"
os.environ["NLP_NER_MODEL"] = "dslim/bert-base-NER-uncased"
os.environ["NLP_BIAS_MODEL"] = "premsa/political-bias-prediction-allsides-BERT"

_STUB_ENV = {
    "INPUT_STREAMS": "user:to.be.nlp",
    "USER_OUTPUT_STREAM": "user:to.be.retrieval",
    "BACKGROUND_OUTPUT_STREAM": "background:to.be.retrieval",
    "FAILURE_OUTPUT_STREAM": "user:failed.nlp",
    "GROUP_NAME": "nlp-group",
    "CONSUMER_NAME": "nlp-consumer",
    "NLP_MAX_WORKERS": "1",
    "BATCH_SIZE": "1",
    "USE_GPU": "false",
}
for k, v in _STUB_ENV.items():
    os.environ.setdefault(k, v)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
log_level = logging.DEBUG if args.debug else logging.INFO
logging.basicConfig(
    level=log_level,
    format="%(asctime)s  %(levelname)-8s  %(name)-30s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("test_components")

# ---------------------------------------------------------------------------
# Project imports (after sys.path and env vars are set)
# ---------------------------------------------------------------------------
from common.models.api.redis_models import Article, Message, MessageHeader, MessagePayload, NLPOptions, NLPResult, SentenceScore, StreamMessage  # noqa: E402
from microservices.nlp.components.bias import BiasDetector  # noqa: E402
from microservices.nlp.components.checkworthy import CheckWorthinessFilter  # noqa: E402
from microservices.nlp.components.embedder import Embedder  # noqa: E402
from microservices.nlp.components.ner import EntityRecognizer  # noqa: E402
from microservices.nlp.components.preprocess import Preprocessor  # noqa: E402
from microservices.nlp.config import DEVICE_CONFIG, model_manager  # noqa: E402

# Prime heavy library imports in the main thread before load_all() spawns worker
# threads — avoids a huggingface_hub circular import that occurs when
# sentence_transformers and transformers are imported concurrently.
import sentence_transformers  # noqa: E402, F401
import transformers  # noqa: E402, F401

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PIPELINE_ORDER = [
    "preprocessor",
    "embedder",
    "ner",
    "bias",
    "checkworthy",
]

COMPONENT_CLASSES = {
    "preprocessor": Preprocessor,
    "embedder": Embedder,
    "ner": EntityRecognizer,
    "bias": BiasDetector,
    "checkworthy": CheckWorthinessFilter,
}

COMPONENT_DISPLAY_NAMES = {
    "preprocessor": "Preprocessor",
    "embedder": "Embedder",
    "ner": "EntityRecognizer",
    "bias": "BiasDetector",
    "checkworthy": "CheckWorthinessFilter",
}

COMPONENT_MODEL_KEYS = {
    "preprocessor": ["SPACY_SENT"],
    "embedder": ["SPACY_SENT", "EMBEDDING"],
    "ner": ["SPACY_SENT", "EMBEDDING", "NER"],
    "bias": ["SPACY_SENT", "EMBEDDING", "BIAS_POLITICAL", "BIAS_SENTIMENT"],
    "checkworthy": ["SPACY_SENT", "EMBEDDING", "NER", "CHECKWORTHY"],
    "all": ["SPACY_SENT", "EMBEDDING", "NER", "BIAS_POLITICAL", "BIAS_SENTIMENT", "CHECKWORTHY"],
}

# Component type tags for dispatch (matching run_pipeline_tests.py)
COMPONENT_TYPES = {
    "preprocessor": "SentenceGenerator",   # run(article, result, options) -> List[SentenceScore]
    "embedder": "SentenceProcessor",       # run(article, result, options, sentences) -> List[SentenceScore]
    "ner": "SentenceConsumer",             # run(article, result, options, sentences) -> None
    "bias": "ArticleProcessor",            # run(article, result, options) -> None
    "checkworthy": "SentenceProcessor",    # run(article, result, options, sentences) -> List[SentenceScore]
}

SEP = "\u2550" * 70  # ══════...


# ---------------------------------------------------------------------------
# Model loading (selective based on --component)
# ---------------------------------------------------------------------------
keys_to_load = COMPONENT_MODEL_KEYS[args.component]
log.info("Loading models for component=%s: %s", args.component, keys_to_load)
model_manager.load_all(keys=keys_to_load)
log.info("Models ready.")


# ---------------------------------------------------------------------------
# Article loading helper
# ---------------------------------------------------------------------------


def load_article(path: str):
    """Load article JSON and return (Article, NLPOptions)."""
    article_path = Path(path)
    if not article_path.is_absolute():
        article_path = WORKSPACE_ROOT / article_path

    if not article_path.exists():
        log.error("Article file not found: %s", article_path)
        sys.exit(1)

    with open(article_path, encoding="utf-8") as f:
        data = json.load(f)

    article = Article(
        link=data.get("article_url", data.get("url", "http://unknown")),
        title=data.get("article_title", ""),
        text=data.get("article_text", ""),
        summary=data.get("article_summary", ""),
        source=data.get("source", data.get("news_outlet", article_path.stem)),
    )
    options = NLPOptions()
    return article, options


# ---------------------------------------------------------------------------
# Per-component output printers
# ---------------------------------------------------------------------------


def print_preprocessor(result: NLPResult, sentences: list) -> None:
    print(f"  Sentence count: {len(sentences)}")
    for s in sentences[:3]:
        print(f"    [{s.index:02d}] {s.text[:120]}")
    if len(sentences) > 3:
        print(f"    ... and {len(sentences) - 3} more")


def print_embedder(result: NLPResult, sentences: list) -> None:
    if not sentences or sentences[0].embedding is None:
        print("  No embeddings generated.")
        return
    emb = np.array(sentences[0].embedding)
    print(f"  Embedding dims: {len(emb)}")
    print(f"  First embedding -- mean: {emb.mean():.6f}, std: {emb.std():.6f}")
    doc_emb = getattr(result, "doc_embedding", None)
    print(f"  Doc embedding set: {doc_emb is not None}")


def print_centrality(result: NLPResult, sentences: list) -> None:
    ranked = sorted(sentences, key=lambda s: s.score, reverse=True)
    print("  Top 5 sentences by centrality score:")
    for s in ranked[:5]:
        print(f"    [{s.index:02d}] score={s.score:.4f}  {s.text[:80]}")


def print_bias(result: NLPResult, sentences: list) -> None:
    bp = result.bias_profile
    if bp is None:
        print("  No bias profile generated.")
        return
    print(f"  bias_category:               {bp.bias_category}")
    print(f"  bias_analysis_confidence:    {bp.bias_analysis_confidence:.4f}")
    print(f"  sentiment_category:          {bp.sentiment_category}")
    print(f"  sentiment_analysis_confidence: {bp.sentiment_analysis_confidence:.4f}")


def print_ner(result: NLPResult, sentences: list) -> None:
    entities = result.entities_in_article
    print(f"  Entity count: {len(entities)}")
    for e in entities:
        print(f"    {e.type_of_entity:<6}  {e.entity_text}")


def print_checkworthy(result: NLPResult, sentences: list) -> None:
    claims = result.claims_in_article
    print(f"  Claims extracted: {len(claims)}")

    classified = [s for s in sentences if s.claim_type is not None]
    print(f"\n  Sentence classifications ({len(classified)} classified):")
    for s in classified:
        flag = " [CHECK-WORTHY]" if s.is_checkworthy else ""
        print(f"    [{s.index:02d}] type={s.claim_type:<8} conf={s.confidence:.3f}{flag}")
        print(f"         {s.text[:90]}")

    if claims:
        print(f"\n  Claim objects:")
        for i, c in enumerate(claims):
            print(
                f"    [{i}] conf={c.confidence:.3f}"
                f'  "{c.decontextualised_claim_text[:90]}"'
            )


PRINTERS = {
    "preprocessor": print_preprocessor,
    "embedder": print_embedder,
    "centrality": print_centrality,
    "ner": print_ner,
    "bias": print_bias,
    "checkworthy": print_checkworthy,
}


# ---------------------------------------------------------------------------
# Section header printer
# ---------------------------------------------------------------------------


def print_section_header(stage_name: str, elapsed: float) -> None:
    display = COMPONENT_DISPLAY_NAMES[stage_name]
    print(f"\n{SEP}")
    print(f"COMPONENT: {display}  ({elapsed:.3f}s)")
    print(SEP)


# ---------------------------------------------------------------------------
# Single component runner
# ---------------------------------------------------------------------------


def _make_test_stream_message(article: Article) -> StreamMessage:
    """Create a minimal StreamMessage wrapping the given article for testing."""
    header = MessageHeader(
        uid=str(uuid.uuid4()),
        type="user",
        status="processing",
        created_at="2026-01-01T00:00:00Z",
    )
    payload = MessagePayload(
        article_url=article.link,
        parsed_text=article.text,
        title=article.title,
        summary=article.summary,
        news_outlet=article.source,
    )
    message = Message(header=header, payload=payload, stage_timestamps=[])
    return StreamMessage(stream="test", redis_id="0-0", priority=1, data=message)


def run_component(
    name: str,
    article: Article,
    result: NLPResult,
    options: NLPOptions,
    sentences: list,
):
    """Instantiate and run a single component. Returns (elapsed, sentences)."""
    cls = COMPONENT_CLASSES[name]
    ctype = COMPONENT_TYPES[name]

    # Instantiate with correct constructor args per component
    if name == "preprocessor":
        import spacy as _spacy
        _nlp_sm = _spacy.load("en_core_web_sm", disable=["lemmatizer"])
        component = cls(nlp=_nlp_sm)
    elif name in ("bias", "ner", "embedder"):
        component = cls(device_config=DEVICE_CONFIG, model_manager=model_manager)
    elif name == "checkworthy":
        component = cls(device_config=DEVICE_CONFIG)
    else:
        component = cls()

    # Build a StreamMessage so all components get the right second argument
    message = _make_test_stream_message(article)

    # Copy current NLPResult state into the StreamMessage payload
    if result.entities_in_article:
        message.data.payload.entities_in_article = result.entities_in_article
    if result.claims_in_article:
        message.data.payload.claims_in_article = result.claims_in_article
    if result.bias_profile:
        message.data.payload.bias_profile = result.bias_profile

    t0 = time.monotonic()
    if ctype == "SentenceGenerator":
        sentences = component.run(article, message, options)
    elif ctype == "SentenceProcessor":
        sentences = component.run(article, message, options, sentences)
    elif ctype == "SentenceConsumer":
        component.run(article, message, options, sentences)
    else:  # ArticleProcessor
        component.run(article, message, options)

    # Copy results back from StreamMessage to local NLPResult
    msg_result = message.create_nlp_result()
    if msg_result.entities_in_article:
        result.entities_in_article = msg_result.entities_in_article
    if msg_result.claims_in_article:
        result.claims_in_article = msg_result.claims_in_article
    if msg_result.bias_profile:
        result.bias_profile = msg_result.bias_profile

    return time.monotonic() - t0, sentences


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    article_path_str = args.article_json
    target = args.component

    article, options = load_article(article_path_str)

    if not article.text:
        log.error("Article text is empty. Cannot run pipeline.")
        sys.exit(1)

    result = NLPResult()
    sentences: list = []  # tracked locally, not on NLPResult

    if target == "all":
        stages_to_run = PIPELINE_ORDER
        stages_to_print = set(PIPELINE_ORDER)
    else:
        target_idx = PIPELINE_ORDER.index(target)
        stages_to_run = PIPELINE_ORDER[: target_idx + 1]
        stages_to_print = {target}

    total_start = time.monotonic()

    for stage_name in stages_to_run:
        should_print = stage_name in stages_to_print
        try:
            elapsed, sentences = run_component(
                stage_name, article, result, options, sentences
            )
        except Exception as exc:
            if should_print:
                print_section_header(stage_name, 0.0)
                print(f"  ERROR in {COMPONENT_DISPLAY_NAMES[stage_name]}: {exc}")
                traceback.print_exc()
                sys.exit(1)
            else:
                log.warning(
                    "Upstream component %s failed (continuing): %s", stage_name, exc
                )
            continue

        if should_print:
            print_section_header(stage_name, elapsed)
            PRINTERS[stage_name](result, sentences)

    if target == "all":
        total_elapsed = time.monotonic() - total_start
        print(f"\n{SEP}")
        print(f"TOTAL TIME: {total_elapsed:.3f}s")
        print(SEP)


if __name__ == "__main__":
    main()
