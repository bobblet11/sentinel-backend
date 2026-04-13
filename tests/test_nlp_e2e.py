"""
End-to-end NLP pipeline test using the same code path as production.

Production path:
    StreamMessage (from Redis)
        → NLPService._analyze_html_and_update(message)
            → Article built from message fields
            → ClaimExtraction.run(article, message, options)   # ArticleProcessor
        → results read from message.data.payload

This script replicates that path exactly. It does NOT bypass the StreamMessage
layer or pass NLPResult directly (which is what the old run_pipeline_tests.py
incorrectly did).

Usage (from workspace root, inside the NLP container or with models available):
    python tests/test_nlp_e2e.py
    python tests/test_nlp_e2e.py --debug
    python tests/test_nlp_e2e.py --articles bbc_001.json fox_001.json
"""

import argparse
import datetime
import json
import logging
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Path setup — must happen before any project imports
# ---------------------------------------------------------------------------
WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKSPACE_ROOT))

ARTICLES_DIR = WORKSPACE_ROOT / "microservices" / "nlp" / "tests" / "debug_articles"

# ---------------------------------------------------------------------------
# Argument parsing (before imports so env vars are set before config loads)
# ---------------------------------------------------------------------------
parser = argparse.ArgumentParser(description="E2E NLP pipeline test using production code path.")
parser.add_argument("--debug", action="store_true", help="Enable DEBUG logging")
parser.add_argument(
    "--articles",
    nargs="+",
    metavar="FILE",
    help="Specific article JSON filenames to test (default: all in debug_articles/)",
)
args = parser.parse_args()

# ---------------------------------------------------------------------------
# Environment setup — mirrors what the NLP container sets at startup
# ---------------------------------------------------------------------------
os.environ.setdefault("DUMMY_NLP_MODE", "false")
os.environ.setdefault("USE_GPU", "false")
os.environ.setdefault("ENABLE_DECONTEXTUALIZATION", "true")

_NLP_TEST_CACHE = WORKSPACE_ROOT / "microservices" / "nlp" / "tests" / ".cache" / "huggingface"
os.environ.setdefault("HF_HOME", str(_NLP_TEST_CACHE))
os.environ.setdefault("TRANSFORMERS_CACHE", str(_NLP_TEST_CACHE / "hub"))

os.environ["NLP_EMBEDDING_MODEL"] = "sentence-transformers/all-mpnet-base-v2"
os.environ["NLP_NER_MODEL"] = "dslim/bert-base-NER-uncased"
os.environ["NLP_BIAS_MODEL"] = "premsa/political-bias-prediction-allsides-BERT"

# Stub service-level env vars required by config.py at import time
_STUB_ENV = {
    "INPUT_STREAMS": "user:to.be.nlp",
    "USER_OUTPUT_STREAM": "user:to.be.retrieval",
    "BACKGROUND_OUTPUT_STREAM": "background:to.be.retrieval",
    "FAILURE_OUTPUT_STREAM": "user:failed.nlp",
    "GROUP_NAME": "nlp-group",
    "CONSUMER_NAME": "nlp-consumer",
    "NLP_MAX_WORKERS": "1",
    "BATCH_SIZE": "1",
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
    force=True,
)
if not args.debug:
    for noisy in ("transformers", "sentence_transformers", "torch", "filelock", "urllib3", "flair"):
        logging.getLogger(noisy).setLevel(logging.ERROR)

log = logging.getLogger("test_nlp_e2e")

# ---------------------------------------------------------------------------
# Project imports
# ---------------------------------------------------------------------------
import sentence_transformers  # noqa: E402, F401 — prime before parallel model load
import transformers            # noqa: E402, F401

from common.models.api.redis_models import (  # noqa: E402
    Article,
    Message,
    MessageHeader,
    MessagePayload,
    NLPOptions,
    StreamMessage,
)
from microservices.nlp.components.claimextract import ClaimExtraction  # noqa: E402
from microservices.nlp.config import DEVICE_CONFIG, model_manager      # noqa: E402

EMBEDDING_DIM = 768
SEP  = "=" * 78
SEP2 = "-" * 78


# ---------------------------------------------------------------------------
# StreamMessage construction — mirrors the scraper's output message exactly
# ---------------------------------------------------------------------------

def build_stream_message(
    article_url: str,
    title: str,
    parsed_text: str,
    news_outlet: str,
    publish_date: Optional[str] = None,
    author: Optional[str] = None,
    summary: Optional[str] = None,
) -> StreamMessage:
    """
    Constructs a StreamMessage identical to what the web scraper publishes
    onto the user:to.be.nlp stream in production.
    """
    uid = str(uuid.uuid4())
    header = MessageHeader(
        uid=uid,
        type="user",
        status="nlp",
        created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    )
    payload = MessagePayload(
        article_url=article_url,
        news_outlet=news_outlet,
        title=title,
        parsed_text=parsed_text,
        publish_date=publish_date,
        author=author,
        summary=summary,
    )
    message = Message(header=header, payload=payload, stage_timestamps=[])
    return StreamMessage(stream="user:to.be.nlp", redis_id="0-0", priority=1, data=message)


# ---------------------------------------------------------------------------
# Production pipeline runner
# ---------------------------------------------------------------------------

def run_pipeline(message: StreamMessage, pipeline: ClaimExtraction, options: NLPOptions) -> float:
    """
    Runs the pipeline exactly as NLPService._analyze_html_and_update() does:
      1. Build Article from message fields
      2. Call ClaimExtraction.run(article, message, options)
      3. Results land in message.data.payload

    Returns elapsed seconds.
    """
    article = Article(
        text=message.text,
        title=message.title,
        link=message.link,
    )
    t0 = time.monotonic()
    pipeline.run(article, message, options)
    return time.monotonic() - t0


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate(message: StreamMessage) -> Tuple[bool, List[str]]:
    """
    Validates what the retrieval layer will receive.
    Returns (passed, list_of_failures).
    """
    payload = message.data.payload
    failures: List[str] = []

    # --- Bias profile ---
    if payload.bias_profile is None:
        failures.append("bias_profile is None")
    else:
        bp = payload.bias_profile
        if not bp.bias_category:
            failures.append("bias_profile.bias_category is empty")
        if bp.bias_analysis_confidence is None:
            failures.append("bias_profile.bias_analysis_confidence is None")

    # --- Claims ---
    claims = payload.claims_in_article or []
    if not claims:
        failures.append("claims_in_article is empty")
    else:
        null_emb = [i for i, c in enumerate(claims) if c.decontextualised_claim_embedding is None]
        if null_emb:
            failures.append(f"claims with null embedding: indices {null_emb}")

        wrong_dim = [
            i for i, c in enumerate(claims)
            if c.decontextualised_claim_embedding is not None
            and len(c.decontextualised_claim_embedding) != EMBEDDING_DIM
        ]
        if wrong_dim:
            failures.append(
                f"claims with wrong embedding dim (expected {EMBEDDING_DIM}): indices {wrong_dim}"
            )

    # --- Entities ---
    entities = payload.entities_in_article or []
    if not entities:
        failures.append("entities_in_article is empty")

    return len(failures) == 0, failures


# ---------------------------------------------------------------------------
# Pretty printer
# ---------------------------------------------------------------------------

def print_result(article_name: str, message: StreamMessage, elapsed: float, failures: List[str]) -> None:
    payload = message.data.payload
    passed = len(failures) == 0

    status = "PASS" if passed else "FAIL"
    print(f"\n{SEP}")
    print(f"[{status}]  {article_name}  ({elapsed:.1f}s)")
    print(SEP)

    # Bias
    bp = payload.bias_profile
    if bp:
        print(f"  Bias      : {bp.bias_category}  (conf={bp.bias_analysis_confidence:.3f})")
        print(f"  Sentiment : {bp.sentiment_category}  (conf={bp.sentiment_analysis_confidence:.3f})")
    else:
        print("  Bias      : MISSING")

    # Claims
    claims = payload.claims_in_article or []
    print(f"  Claims    : {len(claims)}")
    for i, c in enumerate(claims[:3]):
        emb_status = f"{len(c.decontextualised_claim_embedding)}-dim" if c.decontextualised_claim_embedding else "NO EMBEDDING"
        ents = ", ".join(f"{e.entity_text}[{e.type_of_entity}]" for e in c.NER_entities) or "—"
        print(f"    [{i}] conf={c.confidence:.2f}  emb={emb_status}")
        print(f"         \"{c.decontextualised_claim_text[:90]}\"")
        print(f"         entities: {ents}")
    if len(claims) > 3:
        print(f"    ... and {len(claims) - 3} more")

    # Entities
    entities = payload.entities_in_article or []
    print(f"  Entities  : {len(entities)}")
    for e in entities[:5]:
        print(f"    {e.type_of_entity:<8} {e.entity_text}")
    if len(entities) > 5:
        print(f"    ... and {len(entities) - 5} more")

    # Failures
    if failures:
        print(f"\n  FAILURES:")
        for f in failures:
            print(f"    ✗ {f}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    # Resolve article files
    if args.articles:
        article_files = []
        for name in args.articles:
            p = ARTICLES_DIR / name
            if not p.exists():
                log.error("Article not found: %s", p)
                sys.exit(1)
            article_files.append(p)
    else:
        article_files = sorted(ARTICLES_DIR.glob("*.json"))

    if not article_files:
        log.error("No article JSON files found in %s", ARTICLES_DIR)
        sys.exit(1)

    log.info("Loading NLP models...")
    model_manager.load_all()

    health = model_manager.health_check()
    required_errors = {
        k: v
        for k, v in health.items()
        if v == "error" and model_manager._registry[k].required
    }
    optional_errors = {
        k: v
        for k, v in health.items()
        if v == "error" and not model_manager._registry[k].required
    }
    if optional_errors:
        log.warning("Optional models failed to load (pipeline will degrade gracefully): %s", list(optional_errors))
    if required_errors:
        log.error("Required models failed — cannot run pipeline: %s", required_errors)
        if "SPACY_SENT" in required_errors:
            log.error("  Fix: python -m spacy download en_core_web_sm")
        sys.exit(1)
    log.info("Required models ready. Optional failures: %s", list(optional_errors))

    # Build pipeline (one instance, reused across articles — same as production)
    options = NLPOptions()
    pipeline = ClaimExtraction(device_config=DEVICE_CONFIG, model_manager=model_manager)

    results: List[Dict[str, Any]] = []

    for path in article_files:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        article_url   = data.get("article_url", data.get("url", "http://unknown"))
        title         = data.get("article_title", "")
        parsed_text   = data.get("article_text", "")
        news_outlet   = data.get("source", data.get("news_outlet", path.stem))
        publish_date  = data.get("scraped_at")
        author        = data.get("author")
        summary       = data.get("article_summary", "")

        message = build_stream_message(
            article_url=article_url,
            title=title,
            parsed_text=parsed_text,
            news_outlet=news_outlet,
            publish_date=publish_date,
            author=author,
            summary=summary,
        )

        log.info("Processing %s (%d words)...", path.name, len(parsed_text.split()))
        try:
            elapsed = run_pipeline(message, pipeline, options)
            passed, failures = validate(message)
        except Exception as exc:
            log.exception("Pipeline crashed on %s", path.name)
            elapsed = 0.0
            passed = False
            failures = [f"CRASH: {exc}"]

        print_result(path.name, message, elapsed, failures)
        results.append({"file": path.name, "passed": passed, "failures": failures, "elapsed": elapsed})

    # Summary
    total   = len(results)
    passed  = sum(1 for r in results if r["passed"])
    failed  = total - passed

    print(f"\n{SEP}")
    print(f"SUMMARY  {passed}/{total} passed")
    print(SEP)
    for r in results:
        icon = "PASS" if r["passed"] else "FAIL"
        print(f"  [{icon}]  {r['file']:<25}  {r['elapsed']:.1f}s")
        for f in r["failures"]:
            print(f"           ✗ {f}")

    print(SEP)
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
