"""
debug_model_manager.py
======================
Comprehensive diagnostic script for the NLP pipeline after ModelManager
centralization refactor.

Run with:
    conda run -n sentinel-env python microservices/nlp/tests/debug_model_manager.py 2>&1 | tee /tmp/nlp_debug_output.txt

Tests:
    Section A - ModelManager lifecycle (register, load single, health checks)
    Section B - load_all() for all NLP pipeline models
    Section C - Per-component tests with injected models, full pipeline per article
    Section D - Summary table
"""

import sys
import os
import time
import traceback
import logging
from typing import Any, Dict, List, Optional, Tuple

# ── Env overrides MUST come before any project imports ──────────────────────
# Step 1: Set DUMMY_NLP_MODE=false BEFORE importing anything from microservices.nlp
os.environ["DUMMY_NLP_MODE"] = "false"

# Point HuggingFace to the NLP-local cache which has complete model.safetensors files.
# The root .cache/huggingface/hub has an incomplete blob for typeform/distilbert-base-uncased-mnli.
# microservices/nlp/.cache/huggingface/hub has complete safetensors for all needed models.
os.environ["HF_HOME"] = "/workspaces/sentinel-backend/microservices/nlp/.cache/huggingface"
os.environ["TRANSFORMERS_CACHE"] = "/workspaces/sentinel-backend/microservices/nlp/.cache/huggingface/hub"
os.environ["TRANSFORMERS_OFFLINE"] = "1"  # Hard-offline: fail fast, no hanging

# Use locally cached model variants (checked against .cache/huggingface/hub/)
# Default EMBEDDING=all-MiniLM-L6-v2 is NOT cached; use all-mpnet-base-v2 instead.
# Default BIAS=facebook/bart-large-mnli is NOT cached; use typeform/distilbert-base-uncased-mnli.
# Default CHECKWORTHY=valhalla/distilbart-mnli-12-3 is NOT cached; same typeform model.
# Default NER=dslim/bert-base-NER is cached as the uncased variant.
os.environ["NLP_EMBEDDING_MODEL"] = "sentence-transformers/all-mpnet-base-v2"
os.environ["NLP_NER_MODEL"] = "dslim/bert-base-NER-uncased"
os.environ["NLP_BIAS_MODEL"] = "typeform/distilbert-base-uncased-mnli"
os.environ["NLP_CHECKWORTHY_MODEL"] = "typeform/distilbert-base-uncased-mnli"

# Stub the stream/service env vars that config.py reads at import time.
# These are not needed for component-level testing.
os.environ.setdefault("INPUT_STREAMS", "user:to.be.nlp,background:to.be.nlp")
os.environ.setdefault("USER_OUTPUT_STREAM", "user:to.be.retrieval")
os.environ.setdefault("BACKGROUND_OUTPUT_STREAM", "background:to.be.retrieval")
os.environ.setdefault("FAILURE_OUTPUT_STREAM", "user:failed.nlp")
os.environ.setdefault("GROUP_NAME", "nlp-group")
os.environ.setdefault("CONSUMER_NAME", "nlp-consumer-1")
os.environ.setdefault("NLP_MAX_WORKERS", "2")
os.environ.setdefault("BATCH_SIZE", "4")

# Step 1: Add repo root to sys.path
sys.path.insert(0, "/workspaces/sentinel-backend")

logging.basicConfig(
    level=logging.WARNING,  # Suppress INFO noise during inference; we print our own output
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("debug-model-manager")

# ── Test articles (5 diverse types per instructions) ─────────────────────────

ARTICLES = {
    "political": """President Biden signed a sweeping executive order on Monday targeting climate change,
    directing federal agencies to cut emissions by 50% before 2030. Senate Republicans immediately condemned
    the move, with Mitch McConnell calling it government overreach. The White House argued the action was
    necessary to meet international commitments made at the Paris Climate Accord. Democrats praised the
    decision, while fossil fuel industry groups threatened legal challenges.""",

    "scientific": """A new study published in Nature Medicine found that mRNA vaccines reduce the risk of
    long COVID by 41% in fully vaccinated individuals. Researchers at Oxford University analyzed data from
    over 500,000 patients across six countries. The study found that booster doses increased protection
    to 63%. Scientists cautioned that the mechanism is not yet fully understood and further trials are needed.
    The findings support continued vaccination campaigns globally.""",

    "short_minimal": """It rained today. The streets were wet.""",

    "opinion": """The government has completely failed its citizens. Politicians only care about donors and
    lobbyists, never ordinary people. The mainstream media is complicit in covering up the truth. We should
    all be outraged at the corrupt establishment that has rigged the system against us for decades.
    Nothing will change until the entire political class is thrown out.""",

    "noisy": """Th3 compny reportsed Q3 earnngs of $2.4B, up 12% YOY!!! CEO John Smyth said 'were very
    exciteed' abuot growwth. EBITDA margins improoved to 18.3%. Reveeneu from cloud segmnt rose 34%.
    The stokc surged 8% in after-hours tradding on Thursdday. Analystts had expectd EPS of $1.20;
    actual EPS came in at $1.31.""",
}

# Persistent per-component, per-article result tracking
# Key: (component_name, article_id) -> dict with status and detail
_results: Dict[Tuple[str, str], Dict[str, Any]] = {}


def record(component: str, article_id: str, status: str, detail: str, elapsed_s: float = 0.0) -> None:
    _results[(component, article_id)] = {
        "status": status,   # PASS | FAIL | WARN | SKIP
        "detail": detail,
        "elapsed_s": round(elapsed_s, 3),
    }


# ── Helpers ──────────────────────────────────────────────────────────────────

def make_article_and_result(article_id: str):
    """Return (Article, NLPResult, NLPOptions) for the given article_id."""
    from common.models.api.redis_models import Article, NLPResult, NLPOptions
    article = Article(
        link=f"https://debug.test/{article_id}",
        title=article_id.replace("_", " ").title(),
        text=ARTICLES[article_id],
    )
    result = NLPResult()
    options = NLPOptions()
    return article, result, options


def section_header(label: str) -> None:
    print(f"\n{'=' * 70}")
    print(f"  {label}")
    print(f"{'=' * 70}")


# ─────────────────────────────────────────────────────────────────────────────
# SECTION A — ModelManager lifecycle
# ─────────────────────────────────────────────────────────────────────────────

def section_a() -> Any:
    """
    Tests:
      A1 - Instantiate ModelManager and register_defaults()
      A2 - health_check() before any load (expect all 'unloaded')
      A3 - Load only SPACY_SENT
      A4 - health_check() after SPACY_SENT load
      A5 - Load EMBEDDING
      A6 - health_check() after two models loaded
      A7 - get() on unloaded key raises ModelNotReadyError
      A8 - get() on unknown key raises ModelNotFoundError

    Returns the ModelManager instance with SPACY_SENT already loaded.
    """
    section_header("SECTION A: ModelManager Lifecycle")

    from common.model_manager.manager import ModelManager
    from common.model_manager.registry import ModelState
    from common.model_manager.exceptions import ModelNotReadyError, ModelNotFoundError

    # A1 — Instantiate + register_defaults
    print("\n[A1] Instantiate ModelManager(device='cpu', dummy_mode=False) + register_defaults()")
    mm = ModelManager(device="cpu", dummy_mode=False)
    mm.register_defaults()
    print(f"     Registered keys: {list(mm._registry.keys())}")

    # A2 — health_check before loading (all unloaded)
    print("\n[A2] health_check() before any load — expect all 'unloaded'")
    health_before = mm.health_check()
    for k, v in health_before.items():
        print(f"     {k}: {v}")
    all_unloaded = all(v == "unloaded" for v in health_before.values())
    status_a2 = "PASS" if all_unloaded else "FAIL"
    print(f"     => {status_a2}: all unloaded = {all_unloaded}")
    record("A2.health_check_before_load", "core", status_a2,
           f"all_unloaded={all_unloaded}, keys={list(health_before.keys())}")

    # A3 — Load SPACY_SENT
    print("\n[A3] Load SPACY_SENT (fastest, no download)")
    t0 = time.perf_counter()
    mm.load("SPACY_SENT")
    t_spacy = time.perf_counter() - t0
    state_spacy = mm.get_state("SPACY_SENT")
    status_a3 = "PASS" if state_spacy == ModelState.READY else "FAIL"
    print(f"     state={state_spacy.value}, load_time={t_spacy:.2f}s => {status_a3}")
    record("A3.load_SPACY_SENT", "core", status_a3,
           f"state={state_spacy.value}", elapsed_s=t_spacy)

    # A4 — health_check after SPACY_SENT
    print("\n[A4] health_check() after SPACY_SENT load")
    health_spacy = mm.health_check()
    print(f"     SPACY_SENT={health_spacy['SPACY_SENT']}, EMBEDDING={health_spacy['EMBEDDING']}")
    correct_a4 = health_spacy["SPACY_SENT"] == "ready" and health_spacy["EMBEDDING"] == "unloaded"
    status_a4 = "PASS" if correct_a4 else "FAIL"
    print(f"     => {status_a4}")
    record("A4.health_check_partial", "core", status_a4,
           f"SPACY_SENT={health_spacy['SPACY_SENT']}, EMBEDDING={health_spacy['EMBEDDING']}")

    # A5 — Load EMBEDDING
    print("\n[A5] Load EMBEDDING (sentence-transformers/all-mpnet-base-v2)")
    t0 = time.perf_counter()
    mm.load("EMBEDDING")
    t_embed = time.perf_counter() - t0
    state_embed = mm.get_state("EMBEDDING")
    status_a5 = "PASS" if state_embed == ModelState.READY else "FAIL"
    print(f"     state={state_embed.value}, load_time={t_embed:.2f}s => {status_a5}")
    record("A5.load_EMBEDDING", "core", status_a5,
           f"state={state_embed.value}", elapsed_s=t_embed)

    # A6 — health_check after two models
    print("\n[A6] health_check() after SPACY_SENT + EMBEDDING")
    health_two = mm.health_check()
    for k, v in health_two.items():
        print(f"     {k}: {v}")
    record("A6.health_check_two_models", "core", "PASS",
           str({k: v for k, v in health_two.items()}))

    # A7 — get() on unloaded key raises ModelNotReadyError
    print("\n[A7] get('NER') on unloaded key — expect ModelNotReadyError")
    try:
        mm.get("NER")
        print("     FAIL: no exception raised")
        record("A7.get_unloaded_raises", "core", "FAIL", "No exception raised")
    except ModelNotReadyError as e:
        print(f"     PASS: ModelNotReadyError raised as expected: {e}")
        record("A7.get_unloaded_raises", "core", "PASS", str(e))
    except Exception as e:
        print(f"     FAIL: unexpected exception type {type(e).__name__}: {e}")
        record("A7.get_unloaded_raises", "core", "FAIL", f"{type(e).__name__}: {e}")

    # A8 — get() on unknown key raises ModelNotFoundError
    print("\n[A8] get('NONEXISTENT') — expect ModelNotFoundError")
    try:
        mm.get("NONEXISTENT")
        print("     FAIL: no exception raised")
        record("A8.get_unknown_raises", "core", "FAIL", "No exception raised")
    except ModelNotFoundError as e:
        print(f"     PASS: ModelNotFoundError raised as expected: {e}")
        record("A8.get_unknown_raises", "core", "PASS", str(e))
    except Exception as e:
        print(f"     FAIL: unexpected exception type {type(e).__name__}: {e}")
        record("A8.get_unknown_raises", "core", "FAIL", f"{type(e).__name__}: {e}")

    return mm


# ─────────────────────────────────────────────────────────────────────────────
# SECTION B — load_all() for full NLP pipeline
# ─────────────────────────────────────────────────────────────────────────────

def section_b(mm: Any) -> Dict[str, Any]:
    """
    Loads NER, BIAS, CHECKWORTHY (SPACY_SENT and EMBEDDING already loaded in A).
    Times the entire load_all call.
    Returns dict of model instances keyed by model key.
    """
    section_header("SECTION B: load_all() for Full NLP Pipeline")

    from common.model_manager.registry import ModelState

    keys_to_load = ["NER", "BIAS", "CHECKWORTHY"]
    print(f"\n  Loading keys via individual mm.load(): {keys_to_load}")
    print(f"  (SPACY_SENT and EMBEDDING already loaded in Section A)")

    load_timings: Dict[str, float] = {}

    t_all_start = time.perf_counter()
    for key in keys_to_load:
        t0 = time.perf_counter()
        mm.load(key)
        elapsed = time.perf_counter() - t0
        load_timings[key] = elapsed
        state = mm.get_state(key)
        status = "PASS" if state == ModelState.READY else "FAIL"
        print(f"  [{status}] {key}: state={state.value}, load_time={elapsed:.2f}s")
        record(f"B.load_{key}", "core", status, f"state={state.value}", elapsed_s=elapsed)
    t_all_total = time.perf_counter() - t_all_start

    print(f"\n  Total load time for NER+BIAS+CHECKWORTHY: {t_all_total:.2f}s")

    # Final health_check
    print("\n  Final health_check() — all registered models:")
    health_final = mm.health_check()
    for k, v in health_final.items():
        marker = "OK" if v == "ready" else ("ERR" if v == "error" else "---")
        print(f"    [{marker}] {k}: {v}")

    # Collect model instances (only if READY)
    instances = {}
    for key in ["SPACY_SENT", "EMBEDDING", "NER", "BIAS", "CHECKWORTHY"]:
        state = mm.get_state(key)
        if state == ModelState.READY:
            try:
                instances[key] = mm.get(key)
            except Exception as e:
                print(f"  WARNING: get('{key}') failed even though state=READY: {e}")
                instances[key] = None
        else:
            instances[key] = None
            print(f"  WARNING: {key} not ready (state={state.value}), component tests will be limited")

    record("B.load_all_summary", "core", "PASS",
           f"total_load_s={t_all_total:.2f}, health={health_final}")

    return instances


# ─────────────────────────────────────────────────────────────────────────────
# SECTION C — Component tests (inject loaded models, full pipeline per article)
# ─────────────────────────────────────────────────────────────────────────────

def _run_preprocessor(preprocessor, article_id: str) -> Optional[Any]:
    """Run Preprocessor on article_id. Returns NLPResult or None on failure."""
    from common.models.api.redis_models import NLPResult, NLPOptions, Article
    article, result, options = make_article_and_result(article_id)
    t0 = time.perf_counter()
    try:
        preprocessor.run(article, result, options)
        elapsed = time.perf_counter() - t0
        n = len(result.sentences)
        samples = [s.text[:55] for s in result.sentences[:2]]
        detail = f"sentences={n}, samples={samples}"
        status = "WARN" if n == 0 else "PASS"
        marker = f"PASS(N={n})" if n > 0 else "WARN(N=0)"
        print(f"    [{marker}] Preprocessor / {article_id}: {n} sentences, {elapsed:.3f}s")
        record("Preprocessor", article_id, status, detail, elapsed_s=elapsed)
        return result
    except Exception as e:
        elapsed = time.perf_counter() - t0
        print(f"    [FAIL] Preprocessor / {article_id}: {e}")
        print(traceback.format_exc())
        record("Preprocessor", article_id, "FAIL", f"{type(e).__name__}: {e}", elapsed_s=elapsed)
        return None


def _run_centrality(centrality, article_id: str, result: Any) -> Optional[Any]:
    """Run CentralityScorer on existing result. Embedder must run first."""
    from common.models.api.redis_models import NLPOptions, Article
    article = Article(link=f"https://debug.test/{article_id}", text=ARTICLES[article_id])
    options = NLPOptions()
    t0 = time.perf_counter()
    try:
        centrality.run(article, result, options)
        elapsed = time.perf_counter() - t0
        scores = [s.score for s in result.sentences]
        if not scores:
            detail = "no sentences to score"
            print(f"    [SKIP] CentralityScorer / {article_id}: no sentences")
            record("CentralityScorer", article_id, "SKIP", detail, elapsed_s=elapsed)
        else:
            score_min = min(scores)
            score_max = max(scores)
            top = max(result.sentences, key=lambda s: s.score)
            detail = f"scores=[{score_min:.3f},{score_max:.3f}], top='{top.text[:50]}'"
            print(f"    [PASS] CentralityScorer / {article_id}: range=[{score_min:.3f},{score_max:.3f}]")
            record("CentralityScorer", article_id, "PASS", detail, elapsed_s=elapsed)
        return result
    except Exception as e:
        elapsed = time.perf_counter() - t0
        print(f"    [FAIL] CentralityScorer / {article_id}: {e}")
        print(traceback.format_exc())
        record("CentralityScorer", article_id, "FAIL", f"{type(e).__name__}: {e}", elapsed_s=elapsed)
        return result


def _run_embedder(embedder, article_id: str, result: Any) -> Optional[Any]:
    """Run Embedder on existing result."""
    from common.models.api.redis_models import NLPOptions, Article
    import numpy as np
    article = Article(link=f"https://debug.test/{article_id}", text=ARTICLES[article_id])
    options = NLPOptions()
    t0 = time.perf_counter()
    try:
        if not result.sentences:
            elapsed = time.perf_counter() - t0
            print(f"    [SKIP] Embedder / {article_id}: no sentences")
            record("Embedder", article_id, "SKIP", "no input sentences", elapsed_s=elapsed)
            return result
        embedder.run(article, result, options)
        elapsed = time.perf_counter() - t0
        embs = [s.embedding for s in result.sentences if s.embedding]
        if not embs:
            print(f"    [WARN] Embedder / {article_id}: all embeddings None")
            record("Embedder", article_id, "WARN", "all embeddings None", elapsed_s=elapsed)
        else:
            dim = len(embs[0])
            arr = np.array(embs)
            diversity = float(np.std(arr))
            detail = f"dim={dim}, count={len(embs)}, diversity_std={diversity:.4f}"
            print(f"    [PASS] Embedder / {article_id}: dim={dim}, count={len(embs)}, std={diversity:.4f}, {elapsed:.3f}s")
            record("Embedder", article_id, "PASS", detail, elapsed_s=elapsed)
        return result
    except Exception as e:
        elapsed = time.perf_counter() - t0
        print(f"    [FAIL] Embedder / {article_id}: {e}")
        print(traceback.format_exc())
        record("Embedder", article_id, "FAIL", f"{type(e).__name__}: {e}", elapsed_s=elapsed)
        return result


def _run_ner(ner, article_id: str, result: Any) -> Optional[Any]:
    """Run EntityRecognizer on existing result."""
    from common.models.api.redis_models import NLPOptions, Article
    article = Article(link=f"https://debug.test/{article_id}", text=ARTICLES[article_id])
    options = NLPOptions()
    t0 = time.perf_counter()
    try:
        ner.run(article, result, options)
        elapsed = time.perf_counter() - t0
        entities = result.entities_in_article or []
        n = len(entities)
        samples = [f"{e.entity_text}({e.type_of_entity})" for e in entities[:5]]
        detail = f"count={n}, samples={samples}"
        print(f"    [PASS] EntityRecognizer / {article_id}: {n} entities, {elapsed:.3f}s")
        record("EntityRecognizer", article_id, "PASS", detail, elapsed_s=elapsed)
        return result
    except Exception as e:
        elapsed = time.perf_counter() - t0
        print(f"    [FAIL] EntityRecognizer / {article_id}: {e}")
        print(traceback.format_exc())
        record("EntityRecognizer", article_id, "FAIL", f"{type(e).__name__}: {e}", elapsed_s=elapsed)
        return result


def _run_bias(bias, article_id: str, result: Any) -> Optional[Any]:
    """Run BiasDetector on existing result."""
    from common.models.api.redis_models import NLPOptions, Article
    article = Article(link=f"https://debug.test/{article_id}", text=ARTICLES[article_id])
    options = NLPOptions()
    t0 = time.perf_counter()
    try:
        bias.run(article, result, options)
        elapsed = time.perf_counter() - t0
        bp = result.bias_profile
        if bp is None:
            print(f"    [WARN] BiasDetector / {article_id}: bias_profile=None")
            record("BiasDetector", article_id, "WARN", "bias_profile is None", elapsed_s=elapsed)
        else:
            detail = (
                f"category={bp.bias_category}, score={bp.bias_score:.3f}, "
                f"sentiment={bp.sentiment_category}, sentiment_conf={bp.sentiment_analysis_confidence:.3f}"
            )
            print(f"    [PASS] BiasDetector / {article_id}: {detail}, {elapsed:.3f}s")
            record("BiasDetector", article_id, "PASS", detail, elapsed_s=elapsed)
        return result
    except Exception as e:
        elapsed = time.perf_counter() - t0
        print(f"    [FAIL] BiasDetector / {article_id}: {e}")
        print(traceback.format_exc())
        record("BiasDetector", article_id, "FAIL", f"{type(e).__name__}: {e}", elapsed_s=elapsed)
        return result


def _run_checkworthy(checkworthy, article_id: str, result: Any) -> Optional[Any]:
    """Run CheckWorthinessFilter on existing result."""
    from common.models.api.redis_models import NLPOptions, Article
    article = Article(link=f"https://debug.test/{article_id}", text=ARTICLES[article_id])
    options = NLPOptions()
    t0 = time.perf_counter()
    try:
        if not result.sentences:
            elapsed = time.perf_counter() - t0
            print(f"    [SKIP] CheckWorthinessFilter / {article_id}: no sentences")
            record("CheckWorthinessFilter", article_id, "SKIP", "no sentences", elapsed_s=elapsed)
            return result
        checkworthy.run(article, result, options)
        elapsed = time.perf_counter() - t0
        claims = result.claims_in_article or []
        n_claims = len(claims)
        worthy_sents = [s for s in result.sentences if s.is_checkworthy]
        samples = [c.contextualised_claim_text[:55] for c in claims[:2]]
        detail = f"claims={n_claims}, checkworthy_sents={len(worthy_sents)}, samples={samples}"
        print(f"    [PASS] CheckWorthinessFilter / {article_id}: {n_claims} claims, {elapsed:.3f}s")
        record("CheckWorthinessFilter", article_id, "PASS", detail, elapsed_s=elapsed)
        return result
    except Exception as e:
        elapsed = time.perf_counter() - t0
        print(f"    [FAIL] CheckWorthinessFilter / {article_id}: {e}")
        print(traceback.format_exc())
        record("CheckWorthinessFilter", article_id, "FAIL", f"{type(e).__name__}: {e}", elapsed_s=elapsed)
        return result


def section_c(instances: Dict[str, Any]) -> None:
    """
    Run the full pipeline in order for each article.
    Inject real models from instances dict so no re-loading occurs.

    Pipeline order (matching nlp_service.py):
        Preprocessor -> Embedder -> CentralityScorer -> EntityRecognizer
        -> BiasDetector -> CheckWorthinessFilter

    Note: Embedder must run before CentralityScorer (centrality needs embeddings).
    """
    section_header("SECTION C: Component Tests (Injected Models, Full Pipeline per Article)")

    from microservices.nlp.components.preprocess import Preprocessor
    from microservices.nlp.components.embedder import Embedder
    from microservices.nlp.components.centrality import CentralityScorer
    from microservices.nlp.components.ner import EntityRecognizer
    from microservices.nlp.components.bias import BiasDetector
    from microservices.nlp.components.checkworthy import CheckWorthinessFilter

    # Instantiate components with injected models
    spacy_nlp = instances.get("SPACY_SENT")
    embed_model = instances.get("EMBEDDING")
    ner_model = instances.get("NER")
    bias_model = instances.get("BIAS")
    checkworthy_model = instances.get("CHECKWORTHY")

    preprocessor = Preprocessor(nlp=spacy_nlp)
    embedder = Embedder(model=embed_model)
    centrality = CentralityScorer()
    ner = EntityRecognizer(ner_model=ner_model)

    # BiasDetector and CheckWorthinessFilter fall through to model_manager.get() if
    # the injected model is None — which raises ModelNotReadyError against the global
    # config manager (a different instance). Guard: only construct if model loaded.
    if bias_model is not None:
        bias = BiasDetector(model=bias_model)
    else:
        bias = None
        print("  WARNING: BIAS model failed to load — BiasDetector will be skipped")

    if checkworthy_model is not None:
        checkworthy = CheckWorthinessFilter(classifier=checkworthy_model)
    else:
        checkworthy = None
        print("  WARNING: CHECKWORTHY model failed to load — CheckWorthinessFilter will be skipped")

    print(f"\n  BiasDetector model_mode: {bias.model_mode}")
    print(f"  CheckWorthinessFilter threshold: {checkworthy.threshold}")
    print(f"  CheckWorthinessFilter candidate_labels: {checkworthy.candidate_labels}")

    for article_id in ARTICLES:
        print(f"\n  {'─' * 60}")
        print(f"  Article: {article_id.upper()}")
        print(f"  Text length: {len(ARTICLES[article_id])} chars")
        print(f"  {'─' * 60}")

        # Stage 1: Preprocessor
        result = _run_preprocessor(preprocessor, article_id)
        if result is None:
            # Record all downstream as skipped due to preprocessor failure
            for comp in ["Embedder", "CentralityScorer", "EntityRecognizer", "BiasDetector", "CheckWorthinessFilter"]:
                record(comp, article_id, "SKIP", "Preprocessor failed", elapsed_s=0.0)
            record("FullPipeline", article_id, "FAIL", "Preprocessor failed", elapsed_s=0.0)
            continue

        # Stage 2: Embedder (must run before CentralityScorer)
        result = _run_embedder(embedder, article_id, result)

        # Stage 3: CentralityScorer (needs embeddings from Embedder)
        result = _run_centrality(centrality, article_id, result)

        # Stage 4: EntityRecognizer
        result = _run_ner(ner, article_id, result)

        # Stage 5: BiasDetector (skip if model failed to load)
        if bias is not None:
            result = _run_bias(bias, article_id, result)
        else:
            print(f"    [SKIP] BiasDetector / {article_id}: model not loaded (error state)")
            record("BiasDetector", article_id, "SKIP", "model in ERROR state", elapsed_s=0.0)

        # Stage 6: CheckWorthinessFilter (skip if model failed to load)
        if checkworthy is not None:
            result = _run_checkworthy(checkworthy, article_id, result)
        else:
            print(f"    [SKIP] CheckWorthinessFilter / {article_id}: model not loaded (error state)")
            record("CheckWorthinessFilter", article_id, "SKIP", "model in ERROR state", elapsed_s=0.0)

        # Record full pipeline status
        stages = ["Preprocessor", "Embedder", "CentralityScorer", "EntityRecognizer", "BiasDetector", "CheckWorthinessFilter"]
        failed_stages = [s for s in stages if _results.get((s, article_id), {}).get("status") == "FAIL"]
        warn_stages = [s for s in stages if _results.get((s, article_id), {}).get("status") == "WARN"]

        if failed_stages:
            pipeline_status = "FAIL"
            pipeline_detail = f"failed_stages={failed_stages}"
        elif warn_stages:
            pipeline_status = "WARN"
            pipeline_detail = f"warn_stages={warn_stages}"
        else:
            pipeline_status = "PASS"
            bp = result.bias_profile
            n_sentences = len(result.sentences)
            n_claims = len(result.claims_in_article)
            n_entities = len(result.entities_in_article)
            emb_dim = len(result.sentences[0].embedding) if result.sentences and result.sentences[0].embedding else 0
            pipeline_detail = (
                f"sentences={n_sentences}, claims={n_claims}, entities={n_entities}, "
                f"emb_dim={emb_dim}, bias_score={f'{bp.bias_score:.3f}' if bp else 'N/A'}"
            )

        print(f"\n    => FullPipeline [{pipeline_status}]: {pipeline_detail}")
        record("FullPipeline", article_id, pipeline_status, pipeline_detail)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION D — Summary table
# ─────────────────────────────────────────────────────────────────────────────

def section_d() -> None:
    section_header("SECTION D: Component Performance Summary")

    components = [
        "Preprocessor",
        "Embedder",
        "CentralityScorer",
        "EntityRecognizer",
        "BiasDetector",
        "CheckWorthinessFilter",
        "FullPipeline",
    ]
    article_ids = list(ARTICLES.keys())

    # Column widths
    comp_w = max(len(c) for c in components) + 2
    art_w = 18

    # Header
    header = f"{'Component':<{comp_w}}" + "".join(f"{aid:<{art_w}}" for aid in article_ids)
    print(f"\n{header}")
    print("-" * len(header))

    for comp in components:
        row = f"{comp:<{comp_w}}"
        for aid in article_ids:
            r = _results.get((comp, aid), {})
            status = r.get("status", "---")
            # Short detail extract
            detail = r.get("detail", "")
            elapsed = r.get("elapsed_s", 0.0)

            # Build compact cell
            if status == "PASS":
                # Extract key metric from detail
                if comp == "Preprocessor" and "sentences=" in detail:
                    n = detail.split("sentences=")[1].split(",")[0]
                    cell = f"PASS(N={n})"
                elif comp == "Embedder" and "dim=" in detail:
                    dim = detail.split("dim=")[1].split(",")[0]
                    cnt = detail.split("count=")[1].split(",")[0]
                    cell = f"PASS({cnt}x{dim}d)"
                elif comp == "CentralityScorer" and "scores=" in detail:
                    cell = f"PASS({elapsed:.2f}s)"
                elif comp == "EntityRecognizer" and "count=" in detail:
                    n = detail.split("count=")[1].split(",")[0]
                    cell = f"PASS(N={n})"
                elif comp == "BiasDetector" and "score=" in detail:
                    score = detail.split("score=")[1].split(",")[0]
                    cell = f"PASS({score})"
                elif comp == "CheckWorthinessFilter" and "claims=" in detail:
                    n = detail.split("claims=")[1].split(",")[0]
                    cell = f"PASS(C={n})"
                elif comp == "FullPipeline":
                    cell = f"PASS({elapsed:.2f}s)"
                else:
                    cell = "PASS"
            elif status == "FAIL":
                err_short = detail[:12] if detail else "err"
                cell = f"FAIL"
            elif status == "WARN":
                cell = "WARN"
            elif status == "SKIP":
                cell = "SKIP"
            else:
                cell = "---"

            row += f"{cell:<{art_w}}"
        print(row)

    # Overall counts
    all_statuses = [r.get("status", "---") for r in _results.values()
                    if r.get("status") in ("PASS", "FAIL", "WARN", "SKIP")]
    n_pass = sum(1 for s in all_statuses if s == "PASS")
    n_fail = sum(1 for s in all_statuses if s == "FAIL")
    n_warn = sum(1 for s in all_statuses if s == "WARN")
    n_skip = sum(1 for s in all_statuses if s == "SKIP")

    print(f"\nOverall: PASS={n_pass}  FAIL={n_fail}  WARN={n_warn}  SKIP={n_skip}")

    # List any failures/warnings
    failures = [(k, v) for k, v in _results.items() if v.get("status") == "FAIL"]
    warnings = [(k, v) for k, v in _results.items() if v.get("status") == "WARN"]

    if failures:
        print("\nFAILURES:")
        for (comp, aid), v in failures:
            print(f"  [{comp}][{aid}]: {v.get('detail', '')}")

    if warnings:
        print("\nWARNINGS:")
        for (comp, aid), v in warnings:
            print(f"  [{comp}][{aid}]: {v.get('detail', '')}")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    print("=" * 70)
    print("  NLP Pipeline Debug — Model Manager Centralization Diagnostic")
    print("=" * 70)
    print(f"  Date           : 2026-03-24")
    print(f"  HF_HOME        : {os.environ['HF_HOME']}")
    print(f"  OFFLINE        : {os.environ['TRANSFORMERS_OFFLINE']}")
    print(f"  DUMMY_NLP_MODE : {os.environ['DUMMY_NLP_MODE']}")
    print(f"  EMBEDDING      : {os.environ['NLP_EMBEDDING_MODEL']}")
    print(f"  NER            : {os.environ['NLP_NER_MODEL']}")
    print(f"  BIAS           : {os.environ['NLP_BIAS_MODEL']}")
    print(f"  CHECKWORTHY    : {os.environ['NLP_CHECKWORTHY_MODEL']}")

    overall_t0 = time.perf_counter()

    # Section A: ModelManager lifecycle
    mm = section_a()

    # Section B: Load all remaining models
    instances = section_b(mm)

    # Section C: Component tests
    section_c(instances)

    # Section D: Summary table
    section_d()

    total_elapsed = time.perf_counter() - overall_t0
    print(f"\n  Total script runtime: {total_elapsed:.1f}s")

    # Exit 1 if any failures
    failures = [v for v in _results.values() if v.get("status") == "FAIL"]
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
