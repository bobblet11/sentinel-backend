import sys
import os
import re
import json
import time
import logging
import argparse
import dataclasses
from pathlib import Path
from typing import List, Optional

# ---------------------------------------------------------------------------
# PATH SETUP: workspace root contains 'common/' and 'microservices/'
# ---------------------------------------------------------------------------
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from common.models.api.redis_models import (
    Article, NLPResult, NLPOptions, Claim, Entity, SentenceScore,
)
from microservices.nlp.components.preprocess import Preprocessor
from microservices.nlp.components.ner import EntityRecognizer
from microservices.nlp.components.sentenceextract import SentenceExtraction
from microservices.nlp.components.decontext import Decontextualizer
from microservices.nlp.components.checkworthy import CheckWorthiness
from microservices.nlp.components.embedder import Embedder
from microservices.nlp.config import CLAIM_MIN_CONFIDENCE

TESTS_DIR = Path(os.path.dirname(__file__))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _map_entities_to_sentences(sentences: List[SentenceScore], result: NLPResult) -> None:
    if not sentences or not result.entities_in_article:
        return
    for s_obj in sentences:
        s_obj.entities = [
            ent for ent in result.entities_in_article
            if ent.entity_text.lower() in s_obj.text.lower()
        ]


def _discover_articles() -> List[Path]:
    """Return all article{N}.json files in the tests directory, sorted numerically."""
    pattern = re.compile(r'^article(\d+)\.json$')
    found = []
    for p in TESTS_DIR.iterdir():
        m = pattern.match(p.name)
        if m:
            found.append((int(m.group(1)), p))
    found.sort(key=lambda x: x[0])
    return [p for _, p in found]


def _load_article(json_path: Path) -> Optional[Article]:
    if not json_path.exists():
        print(f"Error: '{json_path}' not found.")
        return None
    with open(json_path) as f:
        data = json.load(f)
    return Article(
        title=data.get('article_title', 'Unknown Title'),
        text=data.get('article_text', ''),
        link=data.get('article_url', 'http://example.com'),
        summary=data.get('article_summary', ''),
    )


def _save_output(result: NLPResult, filename: str) -> None:
    base_name = os.path.splitext(filename)[0]
    out_name = f"test_output_{base_name}.json" if filename != 'article.json' else 'test_output.json'
    out_path = TESTS_DIR / out_name
    with open(out_path, 'w') as f:
        json.dump(dataclasses.asdict(result), f, indent=2, default=str)
    print(f"  Output saved to: {out_path}")


def _print_claims(result: NLPResult) -> None:
    print(f"\n{'='*70}")
    print(f"{'FINAL CLAIMS':^70}")
    print(f"{'='*70}")
    if not result.claims_in_article:
        print("  No claims were extracted.")
    else:
        for i, claim in enumerate(result.claims_in_article, 1):
            print(f"\n  Claim #{i}")
            print(f"    Confidence   : {claim.confidence:.2f}")
            print(f"    Source index : {claim.source_sentence_indices}")
            print(f"    Text         : {claim.decontextualised_claim_text}")
            if claim.NER_entities:
                names = [f"{e.entity_text} ({e.type_of_entity})" for e in claim.NER_entities]
                print(f"    Entities     : {', '.join(names)}")
            if claim.decontextualised_claim_embedding:
                print(f"    Embedding    : [{len(claim.decontextualised_claim_embedding)} dims]")
    print(f"\n  Total Claims   : {len(result.claims_in_article)}")
    print(f"  Total Entities : {len(result.entities_in_article)}")


# ---------------------------------------------------------------------------
# Components — initialised once and re-used across articles
# ---------------------------------------------------------------------------
class PipelineComponents:
    def __init__(self):
        print("\nInitialising pipeline components (models load once)...")
        t = time.time()
        self.pre       = Preprocessor()
        self.ner       = EntityRecognizer()
        self.extractor = SentenceExtraction(use_fp16=True)
        self.decon     = Decontextualizer(use_gpu=True)
        self.cw        = CheckWorthiness()
        self.emb       = Embedder()
        print(f"All models ready in {time.time() - t:.2f}s\n")


# ---------------------------------------------------------------------------
# Single-article pipeline run (uses pre-loaded components)
# ---------------------------------------------------------------------------
def run_article(filename: str, components: PipelineComponents) -> NLPResult:
    article = _load_article(TESTS_DIR / filename)
    if article is None:
        return NLPResult()

    result  = NLPResult()
    options = NLPOptions(min_confidence=CLAIM_MIN_CONFIDENCE, max_claims=10)

    print(f"\n{'='*70}")
    print(f"PIPELINE TEST: {article.title}")
    print(f"{'='*70}\n")

    pipeline_start = time.time()
    sentences: List[SentenceScore] = []

    try:
        t = time.time()
        sentences = components.pre.run(article, result, options)
        print(f"[Stage 1] Preprocessor       : {len(sentences):>4} sentences  ({time.time()-t:.2f}s)")

        t = time.time()
        components.ner.run(article, result, options, sentences)
        print(f"[Stage 2] EntityRecognizer   : {len(result.entities_in_article):>4} entities   ({time.time()-t:.2f}s)")

        t = time.time()
        sentences = components.extractor.run(article, result, options, sentences)
        print(f"[Stage 3] SentenceExtraction : {len(sentences):>4} kept       ({time.time()-t:.2f}s)")

        t = time.time()
        sentences = components.decon.run(article, result, options, sentences)
        print(f"[Stage 4] Decontextualizer   :       complete    ({time.time()-t:.2f}s)")

        t = time.time()
        sentences = components.cw.run(article, result, options, sentences)
        checkworthy_count = sum(1 for s in sentences if s.is_checkworthy)
        print(f"[Stage 5] CheckWorthiness    : {checkworthy_count:>4} checkworthy ({time.time()-t:.2f}s)")

        t = time.time()
        _map_entities_to_sentences(sentences, result)
        print(f"[Stage 5.5] Entity mapping   :       complete    ({time.time()-t:.2f}s)")

        t = time.time()
        sentences = components.emb.run(article, result, options, sentences)
        print(f"[Stage 6] Embedder           : {len(sentences):>4} vectorised  ({time.time()-t:.2f}s)")

        t = time.time()
        min_conf = getattr(options, "min_confidence", CLAIM_MIN_CONFIDENCE)
        result.claims_in_article = [
            Claim(
                confidence=s.confidence,
                source_sentence_indices=[s.index],
                decontextualised_claim_text=s.text,
                decontextualised_claim_embedding=s.embedding,
                NER_entities=s.entities,
            )
            for s in sentences
            if s.is_checkworthy and s.confidence >= min_conf
        ]
        print(f"[Stage 7] Claim conversion   : {len(result.claims_in_article):>4} claims      ({time.time()-t:.2f}s)")

    except Exception as e:
        print(f"\nPipeline execution failed: {e}")
        import traceback
        traceback.print_exc()

    print(f"\nPipeline finished in {time.time() - pipeline_start:.2f}s")
    _print_claims(result)
    _save_output(result, filename)
    return result


# ---------------------------------------------------------------------------
# Batch: run all article{N}.json files using the same loaded components
# ---------------------------------------------------------------------------
def run_all_articles() -> None:
    article_files = _discover_articles()
    if not article_files:
        print(f"No article{{N}}.json files found in {TESTS_DIR}")
        return

    print(f"Found {len(article_files)} article(s): {[p.name for p in article_files]}")

    try:
        components = PipelineComponents()
    except Exception as e:
        print(f"Component initialisation failed: {e}")
        import traceback
        traceback.print_exc()
        return

    batch_start = time.time()
    summary_rows = []

    for article_path in article_files:
        result = run_article(article_path.name, components)
        summary_rows.append((
            article_path.name,
            len(result.claims_in_article),
            len(result.entities_in_article),
        ))

    # ------------------------------------------------------------------
    # Cross-article summary
    # ------------------------------------------------------------------
    total_elapsed = time.time() - batch_start
    print(f"\n{'='*70}")
    print(f"{'BATCH SUMMARY':^70}")
    print(f"{'='*70}")
    print(f"  {'Article':<30} {'Claims':>8} {'Entities':>10}")
    print(f"  {'-'*30} {'-'*8} {'-'*10}")
    for name, claims, entities in summary_rows:
        print(f"  {name:<30} {claims:>8} {entities:>10}")
    print(f"  {'-'*30} {'-'*8} {'-'*10}")
    total_claims   = sum(r[1] for r in summary_rows)
    total_entities = sum(r[2] for r in summary_rows)
    print(f"  {'TOTAL':<30} {total_claims:>8} {total_entities:>10}")
    print(f"\n  Processed {len(article_files)} article(s) in {total_elapsed:.2f}s "
          f"({total_elapsed / len(article_files):.2f}s avg)")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(name)s - %(levelname)s - %(message)s')

    parser = argparse.ArgumentParser(description="NLP pipeline test runner")
    parser.add_argument(
        "article",
        nargs="?",
        help="Article file or number (e.g. '3' or 'article3.json'). Omit with --all.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run the pipeline on every article{N}.json found in the tests directory.",
    )
    args = parser.parse_args()

    if args.all:
        run_all_articles()
    else:
        target = args.article or "article.json"
        if not target.endswith(".json"):
            target = f"article{target}.json"
        try:
            components = PipelineComponents()
        except Exception as e:
            print(f"Component initialisation failed: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
        run_article(target, components)
