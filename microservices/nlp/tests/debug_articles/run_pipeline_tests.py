"""
Run the NLP pipeline directly (no Redis, no API) against a single article JSON
and print the final NLPResult in a readable format (embeddings omitted).

Usage (from /app inside the NLP container, or from workspace root locally):
    python microservices/nlp/tests/debug_articles/run_pipeline_tests.py bbc_001.json
    python microservices/nlp/tests/debug_articles/run_pipeline_tests.py <path/to/article.json>

JSON filenames without a path are resolved relative to the script's own directory
(microservices/nlp/tests/debug_articles/). Full relative or absolute paths also work.

The article JSON must contain:
    article_title   — article headline
    article_text    — full article body
    article_url     — source URL
    article_summary — (optional) summary text
    source / news_outlet — (optional) source name
"""

import argparse
import json
import logging
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List

# ---------------------------------------------------------------------------
# Path setup — must happen before any project imports
# ---------------------------------------------------------------------------
WORKSPACE_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(WORKSPACE_ROOT))

# ---------------------------------------------------------------------------
# Argument parsing (pre-import so we can set env vars before loading config)
# ---------------------------------------------------------------------------
parser = argparse.ArgumentParser(
    description="Run the NLP pipeline on a single article JSON and print the NLPResult."
)
parser.add_argument("article_json", help="Path to the article JSON file to analyse")
parser.add_argument(
    "--debug",
    action="store_true",
    help="Enable DEBUG logging to see decontextualizer internals (default: INFO)",
)
args = parser.parse_args()

os.environ.setdefault("DUMMY_NLP_MODE", "false")

# Point HuggingFace to the cache that contains fully-downloaded model weights.
# microservices/nlp/tests/.cache is the complete cache; the root .cache has only
# partial downloads (tokenizer/config blobs, no model weights) for some models.
_NLP_TEST_CACHE = WORKSPACE_ROOT / "microservices" / "nlp" / "tests" / ".cache" / "huggingface"
_HF_CACHE = str(_NLP_TEST_CACHE)
os.environ.setdefault("HF_HOME", _HF_CACHE)
os.environ.setdefault("TRANSFORMERS_CACHE", str(_NLP_TEST_CACHE / "hub"))

# Use models that are confirmed present in the local cache (see .cache/huggingface/hub/).
os.environ["NLP_EMBEDDING_MODEL"] = "sentence-transformers/all-mpnet-base-v2"
os.environ["NLP_NER_MODEL"] = "dslim/bert-base-NER-uncased"
os.environ["NLP_BIAS_MODEL"] = "premsa/political-bias-prediction-allsides-BERT"

# Stub required service-config env vars that NLP config.py demands at import time.
# These are only used by the stream-based service runner, not by the components themselves.
_STUB_ENV = {
    "INPUT_STREAMS": "user:to.be.nlp",
    "USER_OUTPUT_STREAM": "user:to.be.retrieval",
    "BACKGROUND_OUTPUT_STREAM": "background:to.be.retrieval",
    "FAILURE_OUTPUT_STREAM": "user:failed.nlp",
    "GROUP_NAME": "nlp-group",
    "CONSUMER_NAME": "nlp-consumer",
    "NLP_MAX_WORKERS": "1",
    "BATCH_SIZE": "1",
    "USE_GPU": "true",
}
for k, v in _STUB_ENV.items():
    os.environ.setdefault(k, v)

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Logging (set up early so we can log during model loading)
# ---------------------------------------------------------------------------
log_level = logging.DEBUG if args.debug else logging.INFO
logging.basicConfig(
    level=log_level,
    format="%(asctime)s  %(levelname)-8s  %(name)-30s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("pipeline_test")

# Prime heavy library imports in the main thread before load_all() spawns worker
# threads — avoids a huggingface_hub circular import that occurs when
# sentence_transformers and transformers are imported concurrently.
import sentence_transformers  # noqa: E402, F401
import transformers  # noqa: E402, F401

# ---------------------------------------------------------------------------
# Project imports (after sys.path is set and env vars are in place)
# ---------------------------------------------------------------------------
from common.models.api.redis_models import (Article, NLPOptions,  # noqa: E402
                                            NLPResult)
from microservices.nlp.components.claimextract import \
    ClaimExtraction  # noqa: E402
from microservices.nlp.components.device import DeviceConfig  # noqa: E402
from microservices.nlp.config import model_manager  # noqa: E402

# Load all models before running any component (required even in dummy mode
# because components call model_manager.get() at instantiation time).
log.info("Loading NLP models…")
model_manager.load_all()
log.info("Models ready.")

# ---------------------------------------------------------------------------
# Config — ClaimExtraction is the sole pipeline orchestrator (8 stages)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Pipeline runner
# ---------------------------------------------------------------------------

def run_pipeline(article: Article, options: NLPOptions) -> Dict[str, Any]:
    """Run the full NLP pipeline via ClaimExtraction. Returns result, timings, and errors."""
    result = NLPResult()
    stage_timings: Dict[str, float] = {}
    errors: List[str] = []

    device_config = DeviceConfig.resolve(use_gpu=True)
    claim_extraction = ClaimExtraction(device_config=device_config, model_manager=model_manager)

    t0 = time.monotonic()
    try:
        claim_extraction.run(article, result, options)
        stage_timings["ClaimExtraction"] = round(time.monotonic() - t0, 3)
        log.info(
            f"  [ClaimExtraction] done ({stage_timings['ClaimExtraction']:.3f}s)"
        )
    except Exception as exc:
        stage_timings["ClaimExtraction"] = round(time.monotonic() - t0, 3)
        errors.append(f"ClaimExtraction: {exc}")
        log.error(f"  [ClaimExtraction] ERROR: {exc}")
        traceback.print_exc()

    return {
        "result": result,
        "stage_timings": stage_timings,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Pretty-print NLPResult (no embeddings)
# ---------------------------------------------------------------------------

def print_result(result: "NLPResult", stage_timings: Dict[str, float], errors: List[str]) -> None:
    sep = "=" * 70

    print(f"\n{sep}")
    print("NLP RESULT")
    print(sep)

    # --- Bias ---
    print(f"\nBIAS PROFILE")
    print("-" * 70)
    if result.bias_profile:
        bp = result.bias_profile
        print(f"  conf={bp.bias_analysis_confidence}  category={bp.bias_category}")
    else:
        print("  (none)")

    # --- Entities ---
    entities = result.entities_in_article or []
    print(f"\nENTITIES  ({len(entities)} total)")
    print("-" * 70)
    for e in entities:
        print(f"  {e.type_of_entity:<10} {e.entity_text}")

    # --- Claims ---
    claims = result.claims_in_article or []
    print(f"\nCHECK-WORTHY CLAIMS  ({len(claims)} total)")
    print("-" * 70)
    for i, c in enumerate(claims):
        print(f"  [{i}] conf={c.confidence:.2f}  \"{c.decontextualised_claim_text}\"")
        if c.NER_entities:
            ents = ", ".join(f"{e.entity_text}[{e.type_of_entity}]" for e in c.NER_entities)
            print(f"       entities: {ents}")

    # --- Timings & Errors ---
    print(f"\nSTAGE TIMINGS")
    print("-" * 70)
    for stage, t in stage_timings.items():
        print(f"  {stage:<25} {t:.3f}s")
    print(f"  {'TOTAL':<25} {sum(stage_timings.values()):.3f}s")

    if errors:
        print(f"\nERRORS")
        print("-" * 70)
        for e in errors:
            print(f"  {e}")

    print(f"\n{sep}\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    SCRIPT_DIR = Path(__file__).resolve().parent
    article_path = Path(args.article_json)
    if not article_path.is_absolute():
        # Look in the script's own directory first, then fall back to workspace root
        local_path = SCRIPT_DIR / article_path
        if local_path.exists():
            article_path = local_path
        else:
            article_path = WORKSPACE_ROOT / article_path

    if not article_path.exists():
        log.error(f"Article file not found: {article_path}")
        log.error(f"  Checked: {SCRIPT_DIR / args.article_json}")
        log.error(f"  Checked: {WORKSPACE_ROOT / args.article_json}")
        sys.exit(1)

    with open(article_path, encoding="utf-8") as f:
        data = json.load(f)

    url = data.get("article_url", data.get("url", "http://unknown"))
    title = data.get("article_title", "")
    text = data.get("article_text", "")
    source = data.get("source", data.get("news_outlet", article_path.stem))

    log.info(f"Article: {title[:80]}")
    log.info(f"Source:  {source}  |  Words: {len(text.split())}")
    log.info(f"URL:     {url}")

    article = Article(
        link=url,
        title=title,
        text=text,
        summary=data.get("article_summary", ""),
        source=source,
    )
    options = NLPOptions()

    log.info("Running pipeline…")
    run = run_pipeline(article, options)

    print_result(run["result"], run["stage_timings"], run["errors"])

    if run["errors"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
