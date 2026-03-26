"""
Run the NLP pipeline directly (no Redis, no API) against every article JSON in
tests/debug_articles/ and produce a structured report.

Usage (from workspace root):
    python tests/debug_articles/run_pipeline_tests.py [--dummy]

    --dummy   Use DUMMY_NLP_MODE (fast, no GPU/model required) for a smoke-test run.

Output files (written to the same directory as this script):
    pipeline_test_results.json   — per-article machine-readable results
    pipeline_test_report.txt     — human-readable summary
"""

import argparse
import dataclasses
import json
import logging
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Path setup — must happen before any project imports
# ---------------------------------------------------------------------------
WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKSPACE_ROOT))

# ---------------------------------------------------------------------------
# Argument parsing (pre-import so we can set env vars before loading config)
# ---------------------------------------------------------------------------
parser = argparse.ArgumentParser(description="Run NLP pipeline tests on collected articles")
parser.add_argument(
    "--dummy",
    action="store_true",
    help="Set DUMMY_NLP_MODE=true (NOTE: components still need models loaded; "
         "this only affects NLPService-level short-circuiting, not direct component calls)",
)
args = parser.parse_args()

if args.dummy:
    os.environ["DUMMY_NLP_MODE"] = "true"
else:
    os.environ.setdefault("DUMMY_NLP_MODE", "false")

# Point HuggingFace to locally-cached models so no network download is needed.
_HF_CACHE = str(WORKSPACE_ROOT / ".cache" / "huggingface")
os.environ.setdefault("HF_HOME", _HF_CACHE)
os.environ.setdefault("TRANSFORMERS_CACHE", str(WORKSPACE_ROOT / ".cache" / "huggingface" / "hub"))
os.environ["TRANSFORMERS_OFFLINE"] = "1"   # fail fast rather than hang on download attempts

# Use models that are confirmed present in the local cache (see .cache/huggingface/hub/).
os.environ["NLP_EMBEDDING_MODEL"] = "sentence-transformers/all-mpnet-base-v2"
os.environ["NLP_NER_MODEL"] = "dslim/bert-base-NER-uncased"
os.environ["NLP_BIAS_MODEL"] = "typeform/distilbert-base-uncased-mnli"
os.environ["NLP_CHECKWORTHY_MODEL"] = "typeform/distilbert-base-uncased-mnli"

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
    "USE_GPU": "false",
}
for k, v in _STUB_ENV.items():
    os.environ.setdefault(k, v)

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Logging (set up early so we can log during model loading)
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)-30s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("pipeline_test")

# ---------------------------------------------------------------------------
# Project imports (after sys.path is set and env vars are in place)
# ---------------------------------------------------------------------------
from common.models.api.redis_models import Article, NLPOptions, NLPResult  # noqa: E402
from microservices.nlp.components.bias import BiasDetector  # noqa: E402
from microservices.nlp.components.centrality import CentralityScorer  # noqa: E402
from microservices.nlp.components.checkworthy import CheckWorthinessFilter  # noqa: E402
from microservices.nlp.components.embedder import Embedder  # noqa: E402
from microservices.nlp.components.ner import EntityRecognizer  # noqa: E402
from microservices.nlp.components.preprocess import Preprocessor  # noqa: E402
from microservices.nlp.config import model_manager  # noqa: E402

# Prime heavy library imports in the main thread before load_all() spawns worker
# threads — avoids a huggingface_hub circular import that occurs when
# sentence_transformers and transformers are imported concurrently.
import sentence_transformers  # noqa: E402, F401
import transformers  # noqa: E402, F401

# Load all models before running any component (required even in dummy mode
# because components call model_manager.get() at instantiation time).
log.info("Loading NLP models…")
model_manager.load_all()
log.info("Models ready.")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
ARTICLES_DIR = Path(__file__).parent
OUTPUT_JSON = ARTICLES_DIR / "pipeline_test_results.json"
OUTPUT_TXT = ARTICLES_DIR / "pipeline_test_report.txt"
LATENCY_WARN_S = 60.0  # flag as slow if end-to-end takes longer than this

PIPELINE_ORDER = [
    ("Preprocessor", Preprocessor),
    ("Embedder", Embedder),
    ("CentralityScorer", CentralityScorer),
    ("BiasDetector", BiasDetector),
    ("EntityRecognizer", EntityRecognizer),
    ("CheckWorthinessFilter", CheckWorthinessFilter),
]


# ---------------------------------------------------------------------------
# Pipeline runner
# ---------------------------------------------------------------------------

def run_pipeline(article: Article, options: NLPOptions) -> Dict[str, Any]:
    """
    Run all NLP components in order. Returns a dict with timing, counts, errors.
    """
    result = NLPResult()
    stage_timings: Dict[str, float] = {}
    errors: List[str] = []
    last_stage = "init"

    for name, ComponentClass in PIPELINE_ORDER:
        component = ComponentClass()
        t0 = time.monotonic()
        try:
            component.run(article, result, options)
            stage_timings[name] = round(time.monotonic() - t0, 3)
            last_stage = name
        except Exception as exc:
            stage_timings[name] = round(time.monotonic() - t0, 3)
            errors.append(f"{name}: {exc}")
            log.error(f"  [{name}] ERROR: {exc}")
            traceback.print_exc()
            break  # downstream components depend on upstream output

    bias_score: Optional[float] = None
    bias_category: Optional[str] = None
    if result.bias_profile:
        bias_score = result.bias_profile.bias_score
        bias_category = result.bias_profile.bias_category

    return {
        "result": result,
        "stage_timings": stage_timings,
        "errors": errors,
        "last_stage_reached": last_stage,
        "sentence_count": len(result.sentences) if result.sentences else 0,
        "claim_count": len(result.claims_in_article) if result.claims_in_article else 0,
        "entity_count": len(result.entities_in_article) if result.entities_in_article else 0,
        "bias_score": bias_score,
        "bias_category": bias_category,
    }


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

REQUIRED_FIELDS = {"sentences", "claims_in_article", "entities_in_article", "bias_profile"}


def validate_result(run: Dict[str, Any], source_name: str) -> List[str]:
    """Return a list of warning strings for a completed run."""
    warnings = []
    result: NLPResult = run["result"]

    if run["sentence_count"] == 0:
        warnings.append("No sentences extracted — possible preprocessing failure")

    if run["entity_count"] == 0 and source_name in ("BBC News", "Reuters", "AP News"):
        warnings.append(
            f"Zero entities for entity-rich source '{source_name}' — NER may be broken"
        )

    total_latency = sum(run["stage_timings"].values())
    if total_latency > LATENCY_WARN_S:
        warnings.append(f"Latency {total_latency:.1f}s exceeds threshold ({LATENCY_WARN_S}s)")

    return warnings


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def load_article_files() -> List[Path]:
    return sorted(ARTICLES_DIR.glob("*_001.json"))


def main():
    article_files = load_article_files()

    if not article_files:
        log.error(
            f"No article JSON files found in {ARTICLES_DIR}. "
            "Run fetch_articles.py first."
        )
        sys.exit(1)

    log.info(f"Found {len(article_files)} article file(s) to test.")

    options = NLPOptions()
    all_results = []
    passed = 0
    failed_list = []

    run_start = time.monotonic()

    for path in article_files:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        source_name = data.get("source", path.stem)
        url = data.get("article_url", data.get("url", ""))
        title = data.get("article_title", "")
        text = data.get("article_text", "")
        word_count = data.get("word_count", len(text.split()))

        log.info(f"\n{'─'*60}")
        log.info(f"Testing: [{source_name}]  {title[:70]}…")
        log.info(f"  URL:   {url}")
        log.info(f"  Words: {word_count}")

        article = Article(
            link=url or "http://unknown",
            title=title,
            text=text,
            summary=data.get("article_summary", ""),
            source=source_name,
        )

        t0 = time.monotonic()
        run = run_pipeline(article, options)
        total_s = round(time.monotonic() - t0, 3)

        warnings = validate_result(run, source_name)
        status = "failed" if run["errors"] else "passed"
        if status == "passed":
            passed += 1
        else:
            failed_list.append(source_name)

        log.info(f"  Status:   {status.upper()}")
        log.info(f"  Sentences:{run['sentence_count']}  Claims:{run['claim_count']}  Entities:{run['entity_count']}")
        log.info(f"  Bias:     score={run['bias_score']}  category={run['bias_category']}")
        log.info(f"  Duration: {total_s}s  (stages: {run['stage_timings']})")
        if run["errors"]:
            for e in run["errors"]:
                log.error(f"  ERROR: {e}")
        for w in warnings:
            log.warning(f"  WARN:  {w}")

        all_results.append(
            {
                "file": path.name,
                "source": source_name,
                "url": url,
                "title": title,
                "word_count": word_count,
                "status": status,
                "total_latency_s": total_s,
                "stage_timings": run["stage_timings"],
                "last_stage_reached": run["last_stage_reached"],
                "sentence_count": run["sentence_count"],
                "claim_count": run["claim_count"],
                "entity_count": run["entity_count"],
                "bias_score": run["bias_score"],
                "bias_category": run["bias_category"],
                "errors": run["errors"],
                "warnings": warnings,
            }
        )

    total_duration = round(time.monotonic() - run_start, 1)

    # ------------------------------------------------------------------
    # Write JSON results
    # ------------------------------------------------------------------
    summary = {
        "run_timestamp": datetime.now(timezone.utc).isoformat(),
        "dummy_mode": args.dummy,
        "total_articles": len(all_results),
        "passed": passed,
        "failed": len(failed_list),
        "failed_sources": failed_list,
        "total_duration_s": total_duration,
        "articles": all_results,
    }
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)
    log.info(f"\nJSON results → {OUTPUT_JSON}")

    # ------------------------------------------------------------------
    # Write human-readable report
    # ------------------------------------------------------------------
    lines = []
    lines.append("=" * 70)
    lines.append("SENTINEL NLP PIPELINE TEST REPORT")
    lines.append("=" * 70)
    lines.append(f"Run timestamp : {summary['run_timestamp']}")
    lines.append(f"Dummy mode    : {args.dummy}")
    lines.append(f"Total articles: {len(all_results)}")
    lines.append(f"Passed        : {passed}")
    lines.append(f"Failed        : {len(failed_list)}")
    lines.append(f"Duration      : {total_duration}s")
    lines.append("")
    lines.append(f"{'Source':<20} {'Status':<8} {'Words':>6} {'Sents':>6} {'Claims':>6} {'Ents':>6} {'Bias':>6} {'Lat(s)':>7}  Errors/Warnings")
    lines.append("-" * 110)

    for r in all_results:
        bias = f"{r['bias_score']:.2f}" if r["bias_score"] is not None else "N/A"
        extra = ""
        if r["errors"]:
            extra = "ERR: " + "; ".join(r["errors"])[:60]
        elif r["warnings"]:
            extra = "WRN: " + "; ".join(r["warnings"])[:60]

        lines.append(
            f"{r['source']:<20} {r['status'].upper():<8} {r['word_count']:>6} "
            f"{r['sentence_count']:>6} {r['claim_count']:>6} {r['entity_count']:>6} "
            f"{bias:>6} {r['total_latency_s']:>7.1f}  {extra}"
        )

    lines.append("")
    lines.append("Stage timing averages (seconds):")
    stage_names = [name for name, _ in PIPELINE_ORDER]
    for stage in stage_names:
        times = [r["stage_timings"].get(stage) for r in all_results if r["stage_timings"].get(stage) is not None]
        if times:
            avg = sum(times) / len(times)
            lines.append(f"  {stage:<25} avg={avg:.3f}s  max={max(times):.3f}s")

    lines.append("=" * 70)
    report_text = "\n".join(lines)

    with open(OUTPUT_TXT, "w", encoding="utf-8") as f:
        f.write(report_text)

    print(f"\n{report_text}")
    log.info(f"Report → {OUTPUT_TXT}")

    if failed_list:
        sys.exit(1)


if __name__ == "__main__":
    main()
