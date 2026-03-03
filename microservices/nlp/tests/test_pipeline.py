import sys
import os
import json
import time
import logging
import dataclasses
from pathlib import Path
from typing import List

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


# ---------------------------------------------------------------------------
# Helper: map global NER entities onto each sentence by text overlap
# ---------------------------------------------------------------------------
def _map_entities_to_sentences(sentences: List[SentenceScore], result: NLPResult) -> None:
    if not sentences or not result.entities_in_article:
        return
    for s_obj in sentences:
        s_obj.entities = [
            ent for ent in result.entities_in_article
            if ent.entity_text.lower() in s_obj.text.lower()
        ]


def run_local_pipeline_test(filename: str = "article.json") -> None:
    # ------------------------------------------------------------------
    # 1. Load article
    # ------------------------------------------------------------------
    json_path = os.path.join(os.path.dirname(__file__), filename)
    if not os.path.exists(json_path):
        print(f"Error: '{json_path}' not found.")
        return

    with open(json_path, 'r') as f:
        data = json.load(f)

    article = Article(
        title=data.get('article_title', 'Unknown Title'),
        text=data.get('article_text', ''),
        link=data.get('article_url', 'http://example.com'),
        summary=data.get('article_summary', ''),
    )
    result  = NLPResult()
    options = NLPOptions(min_confidence=CLAIM_MIN_CONFIDENCE, max_claims=10)

    print(f"\n{'='*70}")
    print(f"PIPELINE TEST: {article.title}")
    print(f"{'='*70}\n")

    # ------------------------------------------------------------------
    # 2. Initialise all components
    # ------------------------------------------------------------------
    try:
        pre       = Preprocessor()
        ner       = EntityRecognizer()
        extractor = SentenceExtraction(use_fp16=True)
        decon     = Decontextualizer(use_gpu=True)
        cw        = CheckWorthiness()
        emb       = Embedder()
    except Exception as e:
        print(f"Component initialisation failed: {e}")
        import traceback
        traceback.print_exc()
        return

    # ------------------------------------------------------------------
    # 3. Execute pipeline — local sentences list threaded through stages
    # ------------------------------------------------------------------
    pipeline_start = time.time()
    sentences: List[SentenceScore] = []

    try:
        # Stage 1: Preprocessing → local list
        t = time.time()
        sentences = pre.run(article, result, options)
        print(f"[Stage 1] Preprocessor       : {len(sentences):>4} sentences  ({time.time()-t:.2f}s)")

        # Stage 2: NER → writes to result.entities_in_article only
        t = time.time()
        ner.run(article, result, options, sentences)
        print(f"[Stage 2] EntityRecognizer   : {len(result.entities_in_article):>4} entities   ({time.time()-t:.2f}s)")

        # Stage 3: Extraction + deduplication → filtered local list
        t = time.time()
        sentences = extractor.run(article, result, options, sentences)
        print(f"[Stage 3] SentenceExtraction : {len(sentences):>4} kept       ({time.time()-t:.2f}s)")

        # Stage 4: Decontextualisation → rewrites texts in local list
        t = time.time()
        sentences = decon.run(article, result, options, sentences)
        print(f"[Stage 4] Decontextualizer   :       complete    ({time.time()-t:.2f}s)")

        # Stage 5: Check-worthiness scoring
        t = time.time()
        sentences = cw.run(article, result, options, sentences)
        checkworthy_count = sum(1 for s in sentences if s.is_checkworthy)
        print(f"[Stage 5] CheckWorthiness    : {checkworthy_count:>4} checkworthy ({time.time()-t:.2f}s)")

        # Stage 5.5: Map entities onto sentences
        t = time.time()
        _map_entities_to_sentences(sentences, result)
        print(f"[Stage 5.5] Entity mapping   :       complete    ({time.time()-t:.2f}s)")

        # Stage 6: Embed sentences
        t = time.time()
        sentences = emb.run(article, result, options, sentences)
        print(f"[Stage 6] Embedder           : {len(sentences):>4} vectorised  ({time.time()-t:.2f}s)")

        # Stage 7 — Sentence→Claim  (no raw text duplication; index reference only)
        # Only promote sentences that passed check-worthiness AND meet min_confidence.
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

    total_elapsed = time.time() - pipeline_start
    print(f"\nPipeline finished in {total_elapsed:.2f}s")

    # ------------------------------------------------------------------
    # 4. Print results
    # ------------------------------------------------------------------
    print(f"\n{'='*70}")
    print(f"{'FINAL CLAIMS':^70}")
    print(f"{'='*70}")

    if not result.claims_in_article:
        print("No claims were extracted from this article.")
    else:
        for i, claim in enumerate(result.claims_in_article, 1):
            print(f"\nClaim #{i}")
            print(f"  Confidence   : {claim.confidence:.2f}")
            print(f"  Source index : {claim.source_sentence_indices}")
            print(f"  Text         : {claim.decontextualised_claim_text}")
            if claim.NER_entities:
                names = [f"{e.entity_text} ({e.type_of_entity})" for e in claim.NER_entities]
                print(f"  Entities     : {', '.join(names)}")
            if claim.decontextualised_claim_embedding:
                print(f"  Embedding    : [{len(claim.decontextualised_claim_embedding)} dims]")

    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")
    print(f"  Total Claims   : {len(result.claims_in_article)}")
    print(f"  Total Entities : {len(result.entities_in_article)}")

    # ------------------------------------------------------------------
    # 5. Save JSON output
    # ------------------------------------------------------------------
    base_name = os.path.splitext(filename)[0]
    output_filename = (
        f"test_output_{base_name}.json" if filename != 'article.json' else 'test_output.json'
    )
    output_file = Path(os.path.join(os.path.dirname(__file__), output_filename))
    with open(output_file, 'w') as out_f:
        json.dump(dataclasses.asdict(result), out_f, indent=2, default=str)
    print(f"\n  Output saved to: {output_file}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(name)s - %(levelname)s - %(message)s')

    target_file = 'article.json'
    if len(sys.argv) > 1:
        # Accepts either a bare number ("3") or a full filename ("article3.json")
        arg = sys.argv[1]
        target_file = arg if arg.endswith('.json') else f"article{arg}.json"

    run_local_pipeline_test(target_file)
