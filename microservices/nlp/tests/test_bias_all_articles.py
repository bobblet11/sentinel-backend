"""
Bias detection test across all debug article JSON files.

Runs BiasDetector on every JSON file in debug_articles/ and prints a
summary table with political lean, bias score, sentiment, and confidence
for each article.

Usage (from workspace root):
    python microservices/nlp/tests/test_bias_all_articles.py
    python microservices/nlp/tests/test_bias_all_articles.py --debug
"""

import argparse
import json
import logging
import os
import sys
import time
import uuid
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(WORKSPACE_ROOT))

# ---------------------------------------------------------------------------
# Argument parsing (before imports so env vars are set first)
# ---------------------------------------------------------------------------
parser = argparse.ArgumentParser(description="Run BiasDetector on all debug articles.")
parser.add_argument("--debug", action="store_true", help="Enable DEBUG logging")
args = parser.parse_args()

# ---------------------------------------------------------------------------
# Environment setup
# ---------------------------------------------------------------------------
os.environ.setdefault("DUMMY_NLP_MODE", "false")

_NLP_TEST_CACHE = (
    WORKSPACE_ROOT / "microservices" / "nlp" / "tests" / ".cache" / "huggingface"
)
os.environ.setdefault("HF_HOME", str(_NLP_TEST_CACHE))
os.environ.setdefault("TRANSFORMERS_CACHE", str(_NLP_TEST_CACHE / "hub"))

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
# Logging — force=True overrides any root-logger config set by transformers/HF
# during import, ensuring bias.py errors actually surface.
# ---------------------------------------------------------------------------
log_level = logging.DEBUG if args.debug else logging.INFO
logging.basicConfig(
    level=log_level,
    format="%(asctime)s  %(levelname)-8s  %(name)-30s  %(message)s",
    datefmt="%H:%M:%S",
    force=True,
)
# Silence noisy third-party loggers unless --debug
if not args.debug:
    for noisy in ("transformers", "sentence_transformers", "torch", "filelock", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.ERROR)
log = logging.getLogger("test_bias_all_articles")

# ---------------------------------------------------------------------------
# Project imports
# ---------------------------------------------------------------------------
import transformers  # noqa: E402, F401 — prime import before parallel model loading
import sentence_transformers  # noqa: E402, F401

from common.models.api.redis_models import (  # noqa: E402
    Article,
    Message,
    MessageHeader,
    MessagePayload,
    NLPOptions,
    StreamMessage,
)
from microservices.nlp.components.bias import BiasDetector  # noqa: E402
from microservices.nlp.config import DEVICE_CONFIG, model_manager  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
ARTICLES_DIR = WORKSPACE_ROOT / "microservices" / "nlp" / "tests" / "debug_articles"
SEP = "\u2550" * 78


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_article(path: Path) -> Article:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return Article(
        link=data.get("article_url", data.get("url", "http://unknown")),
        title=data.get("article_title", ""),
        text=data.get("article_text", ""),
        summary=data.get("article_summary", ""),
        source=data.get("source", data.get("news_outlet", path.stem)),
    )


def make_stream_message(article: Article) -> StreamMessage:
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


def run_bias(detector: BiasDetector, article: Article) -> tuple:
    """Run bias detection and return (bias_profile, elapsed_seconds).

    Raises any inference exception directly so the caller can surface it,
    rather than swallowing it into a silent neutral profile.
    """
    message = make_stream_message(article)
    options = NLPOptions()

    # Monkey-patch: temporarily replace the model calls with wrappers that
    # re-raise, so _neutral_profile() fallback doesn't hide the root cause.
    original_pol = detector.political_classifier
    original_sent = detector.sentiment_analyzer
    _inference_error: list = []

    def _checked_pol(text):
        try:
            return original_pol(text)
        except Exception as exc:
            _inference_error.append(("political_classifier", exc))
            raise

    def _checked_sent(text):
        try:
            return original_sent(text)
        except Exception as exc:
            _inference_error.append(("sentiment_analyzer", exc))
            raise

    detector.political_classifier = _checked_pol
    detector.sentiment_analyzer = _checked_sent

    t0 = time.monotonic()
    try:
        detector.run(article, message, options)
    finally:
        detector.political_classifier = original_pol
        detector.sentiment_analyzer = original_sent

    elapsed = time.monotonic() - t0

    if _inference_error:
        component, exc = _inference_error[0]
        print(f"  [INFERENCE ERROR] {component}: {type(exc).__name__}: {exc}")

    result = message.create_nlp_result()
    return result.bias_profile, elapsed


def bias_bar(score: float, width: int = 20) -> str:
    """Simple ASCII bar showing bias score magnitude."""
    filled = round(score * width)
    return "[" + "#" * filled + "-" * (width - filled) + "]"


def lean_label(category: str) -> str:
    labels = {"Left": "◀ Left  ", "Right": "Right ▶", "Center": "● Center"}
    return labels.get(category, category)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    article_files = sorted(ARTICLES_DIR.glob("*.json"))
    if not article_files:
        print(f"No JSON files found in {ARTICLES_DIR}")
        sys.exit(1)

    print(f"\nLoading bias models (BIAS_POLITICAL + BIAS_SENTIMENT)...")
    model_manager.load_all(keys=["BIAS_POLITICAL", "BIAS_SENTIMENT"])

    # Health check — abort early if models failed to load
    health = model_manager.health_check()
    pol_state = health.get("BIAS_POLITICAL", "NOT_REGISTERED")
    sent_state = health.get("BIAS_SENTIMENT", "NOT_REGISTERED")
    print(f"  BIAS_POLITICAL : {pol_state}")
    print(f"  BIAS_SENTIMENT : {sent_state}")
    if pol_state != "ready" or sent_state != "ready":
        print("\nERROR: One or more bias models failed to load. Check logs above.")
        sys.exit(1)
    print("Models ready.\n")

    detector = BiasDetector(device_config=DEVICE_CONFIG, model_manager=model_manager)

    results = []
    errors = []

    for path in article_files:
        try:
            article = load_article(path)
            if not article.text:
                errors.append((path.name, "empty article text"))
                continue

            bias_profile, elapsed = run_bias(detector, article)

            if bias_profile is None:
                errors.append((path.name, "bias_profile is None"))
                continue

            results.append({
                "file": path.name,
                "source": article.source or path.stem,
                "title": article.title[:55] + "..." if len(article.title) > 55 else article.title,
                "bias_category": bias_profile.bias_category,
                "bias_confidence": bias_profile.bias_analysis_confidence,
                "sentiment_category": bias_profile.sentiment_category,
                "sentiment_confidence": bias_profile.sentiment_analysis_confidence,
                "elapsed": elapsed,
            })

        except Exception as exc:
            errors.append((path.name, str(exc)))
            log.exception("Error processing %s", path.name)

    # ── Print results table ──────────────────────────────────────────────────
    print(SEP)
    print(f"{'FILE':<22} {'SOURCE':<15} {'LEAN':<10} {'CONF':>6}  {'BIAS BAR':<22} {'SENTIMENT':<12} {'S.CONF':>6}  {'TIME':>5}")
    print(SEP)

    for r in results:
        print(
            f"{r['file']:<22} "
            f"{r['source'][:14]:<15} "
            f"{lean_label(r['bias_category']):<10} "
            f"{r['bias_confidence']:>6.3f}  "
            f"{bias_bar(r['bias_confidence']):<22} "
            f"{r['sentiment_category']:<12} "
            f"{r['sentiment_confidence']:>6.3f}  "
            f"{r['elapsed']:>4.1f}s"
        )

    print(SEP)
    print(f"Processed {len(results)}/{len(article_files)} articles")

    if errors:
        print(f"\n{'ERRORS':}")
        for fname, msg in errors:
            print(f"  {fname}: {msg}")

    # ── Per-article detail ───────────────────────────────────────────────────
    if results:
        print(f"\n{'DETAIL':}")
        print(SEP)
        for r in results:
            print(f"\n  File    : {r['file']}")
            print(f"  Source  : {r['source']}")
            print(f"  Title   : {r['title']}")
            print(f"  Lean    : {lean_label(r['bias_category'])}  (conf={r['bias_confidence']:.4f})")
            print(f"  Tone    : {r['sentiment_category']}  (conf={r['sentiment_confidence']:.4f})")
        print(SEP)


if __name__ == "__main__":
    main()
