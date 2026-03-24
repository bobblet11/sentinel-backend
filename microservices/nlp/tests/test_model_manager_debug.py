"""
NLP Model Manager Diagnostic Test Script
=========================================
Tests each NLP pipeline component individually and end-to-end after the
ModelManager centralization refactor.

Run with:
    conda run -n sentinel-env python microservices/nlp/tests/test_model_manager_debug.py

Uses locally cached HuggingFace models to avoid downloads:
    - sentence-transformers/all-mpnet-base-v2  (embedding)
    - dslim/bert-base-NER-uncased              (NER)
    - typeform/distilbert-base-uncased-mnli    (bias + checkworthy zero-shot)
"""

import sys
import os
import time
import traceback
import dataclasses
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

# ── Env overrides MUST come before any project imports ──────────────────────
# Point HuggingFace to the local .cache so no network downloads are needed.
os.environ["HF_HOME"] = "/workspaces/sentinel-backend/.cache/huggingface"
os.environ["TRANSFORMERS_CACHE"] = (
    "/workspaces/sentinel-backend/.cache/huggingface/hub"
)
os.environ["TRANSFORMERS_OFFLINE"] = "1"  # Hard-offline: fail fast, no hanging

# Use locally cached model variants
os.environ["NLP_EMBEDDING_MODEL"] = "sentence-transformers/all-mpnet-base-v2"
os.environ["NLP_NER_MODEL"] = "dslim/bert-base-NER-uncased"
os.environ["NLP_BIAS_MODEL"] = "typeform/distilbert-base-uncased-mnli"
os.environ["NLP_CHECKWORTHY_MODEL"] = "typeform/distilbert-base-uncased-mnli"

# Disable dummy mode
os.environ["DUMMY_NLP_MODE"] = "false"

# Stub the env vars that config.py reads at import time (stream names etc.)
# These are not needed for component-level tests but config.py will crash
# if get_env_var raises on missing required vars.
os.environ.setdefault("INPUT_STREAMS", "user:to.be.nlp,background:to.be.nlp")
os.environ.setdefault("USER_OUTPUT_STREAM", "user:to.be.retrieval")
os.environ.setdefault("BACKGROUND_OUTPUT_STREAM", "background:to.be.retrieval")
os.environ.setdefault("FAILURE_OUTPUT_STREAM", "user:failed.nlp")
os.environ.setdefault("GROUP_NAME", "nlp-group")
os.environ.setdefault("CONSUMER_NAME", "nlp-consumer-1")
os.environ.setdefault("NLP_MAX_WORKERS", "2")
os.environ.setdefault("BATCH_SIZE", "4")

# Repo root on sys.path
sys.path.insert(0, "/workspaces/sentinel-backend")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("nlp-debug")

# ── Timing helper ───────────────────────────────────────────────────────────

def timed(fn, *args, **kwargs) -> Tuple[Any, float]:
    """Run fn(*args, **kwargs), return (result, elapsed_seconds)."""
    t0 = time.perf_counter()
    result = fn(*args, **kwargs)
    return result, time.perf_counter() - t0


# ── Test articles ────────────────────────────────────────────────────────────

TEST_ARTICLES = {
    "political": {
        "title": "Senate Passes Sweeping Immigration Reform Bill",
        "url": "https://example.com/political-article",
        "text": (
            "Washington, D.C. — The United States Senate passed a sweeping immigration "
            "reform bill on Thursday by a vote of 62 to 38, marking the most significant "
            "overhaul of the nation's immigration system in more than two decades.\n\n"
            "President Biden signed the legislation into law on Friday afternoon, calling "
            "it 'a historic step forward for American values and the rule of law.' The bill "
            "creates a pathway to citizenship for approximately 11 million undocumented "
            "immigrants who have lived in the United States for more than five years.\n\n"
            "Republican Senator Marco Rubio of Florida voted against the measure, arguing "
            "that border security provisions were insufficient. 'We are rewarding lawbreakers '  "
            "while leaving the border wide open,' Rubio said in a floor speech.\n\n"
            "Democratic Senator Chuck Schumer of New York praised the deal as 'pragmatic and "
            "compassionate.' The Department of Homeland Security estimated implementation "
            "costs at $14 billion over the next decade. The American Civil Liberties Union "
            "welcomed the decision, while conservative advocacy groups pledged to challenge "
            "the bill in court."
        ),
    },
    "scientific": {
        "title": "Scientists Discover New CRISPR Mechanism for Treating Genetic Disorders",
        "url": "https://example.com/scientific-article",
        "text": (
            "Researchers at the Broad Institute of MIT and Harvard have identified a new "
            "CRISPR gene-editing mechanism that allows precise correction of single-nucleotide "
            "variants responsible for thousands of genetic diseases.\n\n"
            "The technique, described in the journal Nature on Wednesday, was tested in mouse "
            "models of sickle cell disease and beta-thalassemia with an 89% correction rate "
            "in target cells. Unlike traditional CRISPR-Cas9, the new method does not cause "
            "double-strand DNA breaks, significantly reducing the risk of off-target mutations.\n\n"
            "Lead author Dr. Jennifer Doudna stated that clinical trials in humans could begin "
            "within three to five years. The World Health Organization estimates that 6,000 "
            "known monogenic diseases affect approximately 300 million people globally.\n\n"
            "The research was funded by the National Institutes of Health with a grant totaling "
            "$24 million. Patent rights are held jointly by MIT and Harvard University. "
            "Independent experts described the findings as 'a major leap forward' in the field "
            "of precision medicine."
        ),
    },
    "short_minimal": {
        "title": "Markets Close Higher",
        "url": "https://example.com/short-article",
        "text": "Stocks rose today. The S&P 500 gained 0.4 percent. Apple was up.",
    },
    "opinion_editorial": {
        "title": "The Left's Radical Agenda Is Destroying America's Economy",
        "url": "https://example.com/opinion-article",
        "text": (
            "Let me be completely clear: the disastrous, reckless, and utterly irresponsible "
            "economic policies being pushed by radical left-wing Democrats are an existential "
            "threat to America's prosperity, freedom, and way of life.\n\n"
            "These socialist elites, drunk on power and contemptuous of hardworking Americans, "
            "want nothing more than to tax job-creators into oblivion, strangle small businesses "
            "with suffocating regulations, and hand over the economy to big government bureaucrats "
            "who have never created a single job in their lives.\n\n"
            "Wake up, America! The Green New Deal is not about saving the planet — it is about "
            "destroying capitalism and replacing it with a command economy controlled by the "
            "radical woke mob. Every single data point tells the same story: freedom works, "
            "socialism fails. Always. Every time. Without exception.\n\n"
            "We must fight back now, before it is too late to save the greatest nation on Earth "
            "from those who despise everything it stands for. Our children's future depends on it."
        ),
    },
    "noisy_mixed": {
        "title": "Tech Roundup: Q3 Earnings, AI Regulation & More!!!",
        "url": "https://example.com/noisy-article",
        "text": (
            "BREAKING!!! Tech giants posted Q3 2025 earnings — here's wut happened lol...\n\n"
            "Apple Inc. reported reveneus of $94.9 bilion, up 6% YoY (year-over-year). "
            "Their iPhone 16 sold 52.3M units dispite supply-chain disruptions in China/Taiwan. "
            "CEO Tim Cook called the results 'incredicble' in a press call Wed. morning at 5:00 PM EST.\n\n"
            "Google (Alphabet) came in at $88.3B total revenue w/ $23.1B in net income. "
            "The DOJ antitrust case against Google's seach monopoly is ongoing — verdict expected Q1 2026???\n\n"
            "Microsoft Azure cloud grew 33% QoQ. Satya Nadella said AI copilot integration "
            "drove adoption. EU regulators fined MSFT €242M for Teams bundling violations last month. "
            "OpenAI valuation hit $157B after $6.6B funding rd. "
            "Meta's Reality Labs lost $4.1B in Q3 alone (ouch!!!). "
            "Amazon AWS = still the market leader with 31% share vs Azure 22% vs Google Cloud 12%."
        ),
    },
}


# ── Result collector ─────────────────────────────────────────────────────────

class TestResult:
    def __init__(self, component: str, article_id: str):
        self.component = component
        self.article_id = article_id
        self.status = "pass"
        self.elapsed_s: float = 0.0
        self.output_summary: str = ""
        self.error: Optional[str] = None
        self.traceback: Optional[str] = None

    def fail(self, error: Exception):
        self.status = "fail"
        self.error = str(error)
        self.traceback = traceback.format_exc()

    def warn(self, msg: str):
        self.status = "warn"
        self.error = msg

    def to_dict(self):
        return {
            "component": self.component,
            "article_id": self.article_id,
            "status": self.status,
            "elapsed_s": round(self.elapsed_s, 3),
            "output_summary": self.output_summary,
            "error": self.error,
            "traceback": self.traceback,
        }


all_results: List[TestResult] = []


def run_test(component: str, article_id: str, fn, *args, **kwargs) -> Any:
    """Execute fn and record result. Returns the return value of fn or None on failure."""
    tr = TestResult(component, article_id)
    t0 = time.perf_counter()
    try:
        ret = fn(*args, **kwargs)
        tr.elapsed_s = time.perf_counter() - t0
        all_results.append(tr)
        return ret
    except Exception as exc:
        tr.elapsed_s = time.perf_counter() - t0
        tr.fail(exc)
        all_results.append(tr)
        logger.error("[FAIL] %s / %s: %s", component, article_id, exc)
        return None


# ── Section A: ModelManager core ─────────────────────────────────────────────

def section_a_model_manager():
    print("\n" + "=" * 60)
    print("SECTION A: ModelManager Core")
    print("=" * 60)

    from common.model_manager.manager import ModelManager
    from common.model_manager.registry import ModelState
    from common.model_manager.exceptions import ModelNotReadyError, ModelNotFoundError

    # A1: Instantiate and register
    tr = TestResult("ModelManager.register_defaults", "core")
    try:
        mm = ModelManager(device="cpu", dummy_mode=False)
        mm.register_defaults()
        health = mm.health_check()
        assert all(v == "unloaded" for v in health.values()), (
            f"Expected all unloaded, got: {health}"
        )
        tr.output_summary = f"Registered {len(health)} models, all in 'unloaded' state: {list(health.keys())}"
        print(f"[PASS] {tr.output_summary}")
    except Exception as exc:
        tr.fail(exc)
        print(f"[FAIL] register_defaults: {exc}")
    all_results.append(tr)

    # A2: Load SPACY_SENT
    tr2 = TestResult("ModelManager.load_SPACY_SENT", "core")
    try:
        mm.load("SPACY_SENT")
        state = mm.get_state("SPACY_SENT")
        assert state == ModelState.READY, f"Expected READY, got {state}"
        obj = mm.get("SPACY_SENT")
        assert obj is not None
        tr2.output_summary = f"SPACY_SENT loaded. State={state.value}. Type={type(obj).__name__}"
        print(f"[PASS] {tr2.output_summary}")
    except Exception as exc:
        tr2.fail(exc)
        print(f"[FAIL] load SPACY_SENT: {exc}")
    all_results.append(tr2)

    # A3: ModelNotReadyError for unloaded key
    tr3 = TestResult("ModelManager.get_unloaded_raises", "core")
    try:
        try:
            mm.get("EMBEDDING")
            tr3.fail(AssertionError("Expected ModelNotReadyError but no exception raised"))
        except ModelNotReadyError as e:
            tr3.output_summary = f"Correctly raised ModelNotReadyError: {e}"
            print(f"[PASS] {tr3.output_summary}")
    except Exception as exc:
        tr3.fail(exc)
        print(f"[FAIL] get_unloaded_raises: {exc}")
    all_results.append(tr3)

    # A4: ModelNotFoundError for unknown key
    tr4 = TestResult("ModelManager.get_unknown_raises", "core")
    try:
        try:
            mm.get("NONEXISTENT_KEY")
            tr4.fail(AssertionError("Expected ModelNotFoundError but no exception raised"))
        except ModelNotFoundError as e:
            tr4.output_summary = f"Correctly raised ModelNotFoundError: {e}"
            print(f"[PASS] {tr4.output_summary}")
    except Exception as exc:
        tr4.fail(exc)
        print(f"[FAIL] get_unknown_raises: {exc}")
    all_results.append(tr4)

    # A5: health_check reflects loaded state
    tr5 = TestResult("ModelManager.health_check_mixed", "core")
    try:
        health2 = mm.health_check()
        spacy_state = health2.get("SPACY_SENT", "missing")
        embed_state = health2.get("EMBEDDING", "missing")
        assert spacy_state == "ready", f"SPACY_SENT should be ready, got {spacy_state}"
        assert embed_state == "unloaded", f"EMBEDDING should be unloaded, got {embed_state}"
        tr5.output_summary = f"Health snapshot correct: SPACY_SENT={spacy_state}, EMBEDDING={embed_state}"
        print(f"[PASS] {tr5.output_summary}")
    except Exception as exc:
        tr5.fail(exc)
        print(f"[FAIL] health_check_mixed: {exc}")
    all_results.append(tr5)

    return mm  # Return manager with SPACY_SENT already loaded


# ── Section B: Preprocessor ──────────────────────────────────────────────────

def section_b_preprocessor(spacy_nlp) -> Dict[str, Any]:
    print("\n" + "=" * 60)
    print("SECTION B: Preprocessor")
    print("=" * 60)

    from common.models.api.redis_models import Article, NLPOptions, NLPResult
    from microservices.nlp.components.preprocess import Preprocessor

    preprocessed = {}
    pre = Preprocessor(nlp=spacy_nlp)

    for art_id, art_data in TEST_ARTICLES.items():
        tr = TestResult("Preprocessor", art_id)
        try:
            article = Article(
                link=art_data["url"],
                title=art_data["title"],
                text=art_data["text"],
            )
            result = NLPResult()
            options = NLPOptions()

            t0 = time.perf_counter()
            pre.run(article, result, options)
            tr.elapsed_s = time.perf_counter() - t0

            n = len(result.sentences) if result.sentences else 0
            samples = [s.text[:60] for s in (result.sentences or [])[:3]]
            tr.output_summary = (
                f"Sentences={n} | samples={samples}"
            )
            if n == 0:
                tr.warn(f"Zero sentences after preprocessing for article '{art_id}'")
                print(f"[WARN] Preprocessor / {art_id}: {tr.output_summary}")
            else:
                print(f"[PASS] Preprocessor / {art_id}: {n} sentences")

            preprocessed[art_id] = result

        except Exception as exc:
            tr.elapsed_s = time.perf_counter() - t0
            tr.fail(exc)
            print(f"[FAIL] Preprocessor / {art_id}: {exc}")
            preprocessed[art_id] = NLPResult()

        all_results.append(tr)

    return preprocessed


# ── Section C: Embedder ───────────────────────────────────────────────────────

def section_c_embedder(embed_model, preprocessed: Dict[str, Any]) -> Dict[str, Any]:
    print("\n" + "=" * 60)
    print("SECTION C: Embedder")
    print("=" * 60)

    import numpy as np
    from common.models.api.redis_models import Article, NLPOptions, NLPResult
    from microservices.nlp.components.embedder import Embedder

    embedded = {}
    emb = Embedder(model=embed_model)

    for art_id, result in preprocessed.items():
        tr = TestResult("Embedder", art_id)
        t0 = time.perf_counter()
        try:
            article = Article(link=TEST_ARTICLES[art_id]["url"])
            options = NLPOptions()

            if not result.sentences:
                tr.warn("Skipped — no sentences from Preprocessor")
                print(f"[SKIP] Embedder / {art_id}: no input sentences")
                embedded[art_id] = result
                all_results.append(tr)
                continue

            emb.run(article, result, options)
            tr.elapsed_s = time.perf_counter() - t0

            # Validate
            embeddings = [s.embedding for s in result.sentences if s.embedding]
            if not embeddings:
                tr.warn("All embeddings are None after Embedder run")
                print(f"[WARN] Embedder / {art_id}: all embeddings None")
            else:
                dim = len(embeddings[0])
                # Check all non-zero
                all_nonzero = all(
                    any(v != 0.0 for v in e) for e in embeddings
                )
                # Check diversity (not all identical)
                arr = np.array(embeddings)
                diversity = float(np.std(arr))
                tr.output_summary = (
                    f"dim={dim}, count={len(embeddings)}, "
                    f"nonzero={all_nonzero}, diversity_std={diversity:.4f}"
                )
                if not all_nonzero:
                    tr.warn(f"Some zero embeddings detected: {tr.output_summary}")
                    print(f"[WARN] Embedder / {art_id}: {tr.output_summary}")
                else:
                    print(f"[PASS] Embedder / {art_id}: {tr.output_summary}")

            embedded[art_id] = result

        except Exception as exc:
            tr.elapsed_s = time.perf_counter() - t0
            tr.fail(exc)
            print(f"[FAIL] Embedder / {art_id}: {exc}")
            embedded[art_id] = result

        all_results.append(tr)

    return embedded


# ── Section D: CentralityScorer ───────────────────────────────────────────────

def section_d_centrality(embedded: Dict[str, Any]) -> Dict[str, Any]:
    print("\n" + "=" * 60)
    print("SECTION D: CentralityScorer")
    print("=" * 60)

    from common.models.api.redis_models import Article, NLPOptions, NLPResult
    from microservices.nlp.components.centrality import CentralityScorer

    scored = {}
    cen = CentralityScorer()

    for art_id, result in embedded.items():
        tr = TestResult("CentralityScorer", art_id)
        t0 = time.perf_counter()
        try:
            article = Article(link=TEST_ARTICLES[art_id]["url"])
            options = NLPOptions()

            if not result.sentences or not result.sentences[0].embedding:
                tr.warn("Skipped — no embeddings")
                print(f"[SKIP] CentralityScorer / {art_id}: no embeddings")
                scored[art_id] = result
                all_results.append(tr)
                continue

            cen.run(article, result, options)
            tr.elapsed_s = time.perf_counter() - t0

            scores = [s.score for s in result.sentences]
            top3 = sorted(
                result.sentences, key=lambda s: s.score, reverse=True
            )[:3]
            top3_texts = [(round(s.score, 4), s.text[:60]) for s in top3]
            tr.output_summary = f"Top-3 by centrality: {top3_texts}"
            print(f"[PASS] CentralityScorer / {art_id}: scores range [{min(scores):.3f},{max(scores):.3f}]")

            scored[art_id] = result

        except Exception as exc:
            tr.elapsed_s = time.perf_counter() - t0
            tr.fail(exc)
            print(f"[FAIL] CentralityScorer / {art_id}: {exc}")
            scored[art_id] = result

        all_results.append(tr)

    return scored


# ── Section E: EntityRecognizer ───────────────────────────────────────────────

def section_e_ner(ner_model, scored: Dict[str, Any]) -> Dict[str, Any]:
    print("\n" + "=" * 60)
    print("SECTION E: EntityRecognizer")
    print("=" * 60)

    from common.models.api.redis_models import Article, NLPOptions, NLPResult
    from microservices.nlp.components.ner import EntityRecognizer

    ner_results = {}
    ner = EntityRecognizer(ner_model=ner_model)

    entity_rich_articles = {"political", "scientific", "noisy_mixed"}

    for art_id, result in scored.items():
        tr = TestResult("EntityRecognizer", art_id)
        t0 = time.perf_counter()
        try:
            article = Article(
                link=TEST_ARTICLES[art_id]["url"],
                text=TEST_ARTICLES[art_id]["text"],
            )
            options = NLPOptions()

            ner.run(article, result, options)
            tr.elapsed_s = time.perf_counter() - t0

            entities = result.entities_in_article or []
            n = len(entities)
            samples = [
                f"{e.entity_text}({e.type_of_entity})" for e in entities[:5]
            ]
            tr.output_summary = f"count={n}, samples={samples}"

            if art_id in entity_rich_articles and n == 0:
                tr.warn(f"Expected entities for '{art_id}' but got none")
                print(f"[WARN] EntityRecognizer / {art_id}: {tr.output_summary}")
            else:
                print(f"[PASS] EntityRecognizer / {art_id}: {n} entities")

            ner_results[art_id] = result

        except Exception as exc:
            tr.elapsed_s = time.perf_counter() - t0
            tr.fail(exc)
            print(f"[FAIL] EntityRecognizer / {art_id}: {exc}")
            ner_results[art_id] = result

        all_results.append(tr)

    return ner_results


# ── Section F: BiasDetector ───────────────────────────────────────────────────

def section_f_bias(bias_model, ner_results: Dict[str, Any]) -> Dict[str, Any]:
    print("\n" + "=" * 60)
    print("SECTION F: BiasDetector")
    print("=" * 60)

    from common.models.api.redis_models import Article, NLPOptions, NLPResult
    from microservices.nlp.components.bias import BiasDetector

    bias_results = {}
    bias_det = BiasDetector(model=bias_model)
    print(f"  BiasDetector model_mode: {bias_det.model_mode}")

    for art_id, result in ner_results.items():
        tr = TestResult("BiasDetector", art_id)
        t0 = time.perf_counter()
        try:
            article = Article(
                link=TEST_ARTICLES[art_id]["url"],
                text=TEST_ARTICLES[art_id]["text"],
            )
            options = NLPOptions()

            bias_det.run(article, result, options)
            tr.elapsed_s = time.perf_counter() - t0

            bp = result.bias_profile
            if bp is None:
                tr.warn("bias_profile is None after BiasDetector run")
                print(f"[WARN] BiasDetector / {art_id}: bias_profile=None")
            else:
                tr.output_summary = (
                    f"bias_category={bp.bias_category}, "
                    f"bias_score={bp.bias_score:.3f}, "
                    f"sentiment={bp.sentiment_category}, "
                    f"sentiment_conf={bp.sentiment_analysis_confidence:.3f}"
                )
                print(f"[PASS] BiasDetector / {art_id}: {tr.output_summary}")

            bias_results[art_id] = result

        except Exception as exc:
            tr.elapsed_s = time.perf_counter() - t0
            tr.fail(exc)
            print(f"[FAIL] BiasDetector / {art_id}: {exc}")
            bias_results[art_id] = result

        all_results.append(tr)

    # Bonus: check opinion editorial has higher bias_score than scientific
    tr_reg = TestResult("BiasDetector.regression_check", "cross-article")
    try:
        bp_op = bias_results.get("opinion_editorial") and bias_results["opinion_editorial"].bias_profile
        bp_sci = bias_results.get("scientific") and bias_results["scientific"].bias_profile
        if bp_op and bp_sci:
            if bp_op.bias_score >= bp_sci.bias_score:
                tr_reg.output_summary = (
                    f"PASS: opinion({bp_op.bias_score:.3f}) >= scientific({bp_sci.bias_score:.3f})"
                )
                print(f"[PASS] BiasDetector regression: {tr_reg.output_summary}")
            else:
                tr_reg.warn(
                    f"opinion({bp_op.bias_score:.3f}) < scientific({bp_sci.bias_score:.3f}) — "
                    "expected opinion to score higher bias"
                )
                print(f"[WARN] BiasDetector regression: {tr_reg.error}")
        else:
            tr_reg.warn("Could not compare — one or both bias profiles missing")
    except Exception as exc:
        tr_reg.fail(exc)
    all_results.append(tr_reg)

    return bias_results


# ── Section G: CheckWorthinessFilter ──────────────────────────────────────────

def section_g_checkworthy(checkworthy_model, bias_results: Dict[str, Any]) -> Dict[str, Any]:
    print("\n" + "=" * 60)
    print("SECTION G: CheckWorthinessFilter")
    print("=" * 60)

    from common.models.api.redis_models import Article, NLPOptions, NLPResult
    from microservices.nlp.components.checkworthy import CheckWorthinessFilter

    chk_results = {}
    chk = CheckWorthinessFilter(classifier=checkworthy_model)

    for art_id, result in bias_results.items():
        tr = TestResult("CheckWorthinessFilter", art_id)
        t0 = time.perf_counter()
        try:
            article = Article(link=TEST_ARTICLES[art_id]["url"])
            options = NLPOptions()

            if not result.sentences:
                tr.warn("Skipped — no sentences")
                print(f"[SKIP] CheckWorthinessFilter / {art_id}: no sentences")
                chk_results[art_id] = result
                all_results.append(tr)
                continue

            chk.run(article, result, options)
            tr.elapsed_s = time.perf_counter() - t0

            claims = result.claims_in_article or []
            worthy = [s for s in result.sentences if s.is_checkworthy]
            claim_texts = [c.contextualised_claim_text[:60] for c in claims[:3]]

            tr.output_summary = (
                f"claims={len(claims)}, checkworthy_sents={len(worthy)}, "
                f"samples={claim_texts}"
            )
            print(f"[PASS] CheckWorthinessFilter / {art_id}: {len(claims)} claims")

            chk_results[art_id] = result

        except Exception as exc:
            tr.elapsed_s = time.perf_counter() - t0
            tr.fail(exc)
            print(f"[FAIL] CheckWorthinessFilter / {art_id}: {exc}")
            chk_results[art_id] = result

        all_results.append(tr)

    return chk_results


# ── Section H: End-to-end pipeline ───────────────────────────────────────────

def section_h_end_to_end(spacy_nlp, embed_model, ner_model, bias_model, checkworthy_model):
    print("\n" + "=" * 60)
    print("SECTION H: Full End-to-End Pipeline")
    print("=" * 60)

    from common.models.api.redis_models import Article, NLPOptions, NLPResult
    from microservices.nlp.components.preprocess import Preprocessor
    from microservices.nlp.components.embedder import Embedder
    from microservices.nlp.components.centrality import CentralityScorer
    from microservices.nlp.components.bias import BiasDetector
    from microservices.nlp.components.ner import EntityRecognizer
    from microservices.nlp.components.checkworthy import CheckWorthinessFilter

    pipeline_stages = [
        ("Preprocessor", Preprocessor(nlp=spacy_nlp)),
        ("Embedder", Embedder(model=embed_model)),
        ("CentralityScorer", CentralityScorer()),
        ("BiasDetector", BiasDetector(model=bias_model)),
        ("EntityRecognizer", EntityRecognizer(ner_model=ner_model)),
        ("CheckWorthinessFilter", CheckWorthinessFilter(classifier=checkworthy_model)),
    ]

    e2e_results = {}

    for art_id, art_data in TEST_ARTICLES.items():
        print(f"\n  -- {art_id} --")
        article = Article(
            link=art_data["url"],
            title=art_data["title"],
            text=art_data["text"],
        )
        result = NLPResult()
        options = NLPOptions()

        stage_timings = {}
        total_t0 = time.perf_counter()
        pipeline_ok = True

        for stage_name, component in pipeline_stages:
            tr = TestResult(f"E2E.{stage_name}", art_id)
            t0 = time.perf_counter()
            try:
                component.run(article, result, options)
                tr.elapsed_s = time.perf_counter() - t0
                stage_timings[stage_name] = tr.elapsed_s
            except Exception as exc:
                tr.elapsed_s = time.perf_counter() - t0
                tr.fail(exc)
                print(f"    [FAIL] {stage_name}: {exc}")
                print(traceback.format_exc())
                pipeline_ok = False
                all_results.append(tr)
                break
            all_results.append(tr)

        total_elapsed = time.perf_counter() - total_t0

        if pipeline_ok:
            bp = result.bias_profile
            print(f"    sentences={len(result.sentences)}, "
                  f"claims={len(result.claims_in_article)}, "
                  f"entities={len(result.entities_in_article)}, "
                  f"bias={bp.bias_score if bp else 'N/A':.3f if bp else 'N/A'}, "
                  f"total={total_elapsed:.2f}s")
            print(f"    stage_timings={{{', '.join(f'{k}:{v:.2f}s' for k,v in stage_timings.items())}}}")

        e2e_results[art_id] = {
            "ok": pipeline_ok,
            "result": result,
            "timings": stage_timings,
            "total_s": total_elapsed,
        }

    return e2e_results


# ── Summary printer ───────────────────────────────────────────────────────────

def print_summary():
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    passed = [r for r in all_results if r.status == "pass"]
    warned = [r for r in all_results if r.status == "warn"]
    failed = [r for r in all_results if r.status == "fail"]

    print(f"Total tests : {len(all_results)}")
    print(f"  PASS      : {len(passed)}")
    print(f"  WARN      : {len(warned)}")
    print(f"  FAIL      : {len(failed)}")

    if warned:
        print("\nWARNINGS:")
        for r in warned:
            print(f"  [{r.component}][{r.article_id}] {r.error}")

    if failed:
        print("\nFAILURES:")
        for r in failed:
            print(f"  [{r.component}][{r.article_id}] {r.error}")
            if r.traceback:
                # Only first 10 lines of traceback in summary
                tb_lines = r.traceback.strip().splitlines()[-10:]
                for line in tb_lines:
                    print(f"    {line}")


def save_results_json(e2e_results):
    """Save a machine-readable JSON report for the debug report generator."""
    output = {
        "test_results": [r.to_dict() for r in all_results],
        "e2e_summary": {
            art_id: {
                "ok": v["ok"],
                "total_s": round(v["total_s"], 3),
                "timings": {k: round(t, 3) for k, t in v["timings"].items()},
                "sentences": len(v["result"].sentences) if v["result"].sentences else 0,
                "claims": len(v["result"].claims_in_article) if v["result"].claims_in_article else 0,
                "entities": len(v["result"].entities_in_article) if v["result"].entities_in_article else 0,
                "bias_score": (
                    v["result"].bias_profile.bias_score
                    if v["result"].bias_profile else None
                ),
                "bias_category": (
                    v["result"].bias_profile.bias_category
                    if v["result"].bias_profile else None
                ),
            }
            for art_id, v in e2e_results.items()
        },
    }
    out_path = "/workspaces/sentinel-backend/microservices/nlp/tests/debug_run_output.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nJSON results saved to: {out_path}")
    return output


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("NLP Model Manager Diagnostic Test")
    print(f"HF_HOME={os.environ['HF_HOME']}")
    print(f"TRANSFORMERS_OFFLINE={os.environ['TRANSFORMERS_OFFLINE']}")
    print(f"Models: EMBED={os.environ['NLP_EMBEDDING_MODEL']}, "
          f"NER={os.environ['NLP_NER_MODEL']}, "
          f"BIAS={os.environ['NLP_BIAS_MODEL']}, "
          f"CHECKWORTHY={os.environ['NLP_CHECKWORTHY_MODEL']}")

    # ── A: ModelManager core ─────────────────────────────────────────────────
    mm = section_a_model_manager()

    # ── Pre-load all needed models ───────────────────────────────────────────
    # Load models individually to capture any failures clearly, then use
    # injected instances for component tests (avoids re-loading).
    print("\n" + "=" * 60)
    print("MODEL LOADING (pre-load for component tests)")
    print("=" * 60)

    model_load_timings = {}

    # Load SPACY_SENT (may already be loaded from section A)
    from common.model_manager.registry import ModelState
    if mm.get_state("SPACY_SENT") != ModelState.READY:
        t0 = time.perf_counter()
        mm.load("SPACY_SENT")
        model_load_timings["SPACY_SENT"] = time.perf_counter() - t0
    else:
        model_load_timings["SPACY_SENT"] = 0.0

    for key in ["EMBEDDING", "NER", "BIAS", "CHECKWORTHY"]:
        t0 = time.perf_counter()
        mm.load(key)
        model_load_timings[key] = time.perf_counter() - t0
        state = mm.get_state(key)
        print(f"  {key}: state={state.value} ({model_load_timings[key]:.2f}s)")

    # Retrieve instances
    spacy_nlp = mm.get("SPACY_SENT") if mm.get_state("SPACY_SENT") == ModelState.READY else None
    embed_model = mm.get("EMBEDDING") if mm.get_state("EMBEDDING") == ModelState.READY else None
    ner_model = mm.get("NER") if mm.get_state("NER") == ModelState.READY else None
    bias_model = mm.get("BIAS") if mm.get_state("BIAS") == ModelState.READY else None
    checkworthy_model = mm.get("CHECKWORTHY") if mm.get_state("CHECKWORTHY") == ModelState.READY else None

    print(f"\nModel health after loading:")
    for k, v in mm.health_check().items():
        print(f"  {k}: {v}")

    # ── B–G: Component tests ──────────────────────────────────────────────────
    preprocessed = section_b_preprocessor(spacy_nlp)
    embedded = section_c_embedder(embed_model, preprocessed)
    scored = section_d_centrality(embedded)
    ner_results = section_e_ner(ner_model, scored)
    bias_results = section_f_bias(bias_model, ner_results)
    chk_results = section_g_checkworthy(checkworthy_model, bias_results)

    # ── H: End-to-end ─────────────────────────────────────────────────────────
    e2e_results = section_h_end_to_end(
        spacy_nlp, embed_model, ner_model, bias_model, checkworthy_model
    )

    # ── Final summary ─────────────────────────────────────────────────────────
    print_summary()
    output_data = save_results_json(e2e_results)

    # Return exit code
    failed = [r for r in all_results if r.status == "fail"]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
