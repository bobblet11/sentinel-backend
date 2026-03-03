import logging
import spacy
import time
from typing import List

# Local imports
from microservices.nlp.models.base import ArticleProcessor, SentenceProcessor
from common.models.api.redis_models import Article, Claim, NLPOptions, NLPResult, SentenceScore

# Pipeline stage imports
from microservices.nlp.components.preprocess import Preprocessor
from microservices.nlp.components.ner import EntityRecognizer
from microservices.nlp.components.sentenceextract import SentenceExtraction
from microservices.nlp.components.decontext import Decontextualizer
from microservices.nlp.components.checkworthy import CheckWorthiness
from microservices.nlp.components.embedder import Embedder
from microservices.nlp.components.bias import BiasDetector

logger = logging.getLogger(__name__)


class ClaimExtraction(ArticleProcessor):
    """
    THE PIPELINE ORCHESTRATOR

    Wires all downstream NLP components into a deterministic, staged processing
    sequence. This class owns the entire lifetime of the local
    List[SentenceScore] object — it is the *only* component that writes to
    result.claims_in_article and result.entities_in_article.

    Pipeline Execution Order:
    ┌─────────────────────────────────────────────────────────────────────┐
    │ Stage 1  Preprocessor        text → List[SentenceScore] (local)    │
    │ Stage 2  EntityRecognizer    sentences → result.entities_in_article │
    │ Stage 3  SentenceExtraction  sentences → top-k deduplicated subset  │
    │ Stage 4  Decontextualizer    rewrites each sentence to be           │
    │                              self-contained (original_text stored)  │
    │ Stage 5  CheckWorthiness     scores confidence + is_checkworthy     │
    │ Stage 5.5 Entity Mapping     links global entities to sentences     │
    │ Stage 6  Embedder            produces 768-dim MPNet vectors         │
    │ Stage 7  Sentence→Claim      commits List[SentenceScore] →          │
    │                              result.claims_in_article (no raw text  │
    │                              duplication; uses index references)    │
    │ Stage 8  BiasDetector        article-level political + tone analysis│
    │                              → result.bias_profile (optional)       │
    └─────────────────────────────────────────────────────────────────────┘

    Strategies Applied:
    1.  Local List Pattern: All intermediate sentence data is held in a local
        List[SentenceScore]; NO component writes directly to result until Stage 7.
        This prevents partial writes from corrupting the result on failure.
    2.  Anti-Redundancy (Claim Construction): Claim objects do NOT store raw
        sentence text. Instead, source_sentence_indices references the originating
        SentenceScore.index from the preprocessed token stream, enabling the API
        layer to hydrate text from the article body on demand.
    3.  Entity Mapping (Stage 5.5): Global entities (deduplicated by NER) are
        linked onto each SentenceScore by case-insensitive substring matching,
        enabling per-claim entity metadata without re-running NER per sentence.
    4.  Timing Instrumentation: Each stage's wall-clock latency is logged at INFO
        level to support bottleneck identification in production.
    5.  Conditional BiasDetection: The BiasDetector runs iff
        options.enable_bias_detection is True (default), decoupling it from the
        critical claim-extraction path.
    6.  Graceful Failure: Stage-level exceptions are caught, logged, and re-raised
        so that the service-level error handler can decide on retry semantics.
    """

    def __init__(self, use_gpu: bool = True):
        logger.info("ClaimExtraction: Initializing all pipeline stages...")
        t_start = time.time()

        # Load spaCy once and share across the three components that need it.
        # This avoids loading the same ~100 MB model three separate times.
        try:
            nlp_sm = spacy.load("en_core_web_sm", disable=["ner", "lemmatizer"])
        except OSError:
            logger.error("spaCy model not found. Run: python -m spacy download en_core_web_sm")
            raise

        self.preprocessor        = Preprocessor(nlp=nlp_sm)
        self.entity_recognizer   = EntityRecognizer()
        self.sentence_extractor  = SentenceExtraction(use_fp16=use_gpu)
        self.decontextualizer    = Decontextualizer(use_gpu=use_gpu, nlp=nlp_sm)
        self.checkworthiness     = CheckWorthiness(nlp=nlp_sm)
        self.embedder            = Embedder()
        self.bias_detector       = BiasDetector()

        logger.info(
            f"ClaimExtraction: All models ready in {time.time() - t_start:.2f}s."
        )

    def _map_entities_to_sentences(
        self,
        sentences: List[SentenceScore],
        result: NLPResult,
    ) -> None:
        """
        Links article-level entities onto individual sentences by
        case-insensitive substring match.
        Operates in-place on each SentenceScore.entities list.
        """
        if not sentences or not result.entities_in_article:
            return
        for s_obj in sentences:
            s_obj.entities = [
                ent for ent in result.entities_in_article
                if ent.entity_text.lower() in s_obj.text.lower()
            ]

    def run(self, article: Article, result: NLPResult, options: NLPOptions) -> None:
        """
        Executes the full NLP pipeline end-to-end.
        Writes final data to result.claims_in_article, result.entities_in_article,
        and (if enabled) result.bias_profile.
        """
        pipeline_start = time.time()

        # ── Stage 1 — Preprocessing ─────────────────────────────────────────────
        t = time.time()
        try:
            sentences: List[SentenceScore] = self.preprocessor.run(article, result, options)
        except Exception as e:
            logger.error(f"ClaimExtraction [Stage 1 Preprocessor] failed: {e}")
            raise
        logger.info(
            f"[Stage 1 | Preprocessor] {len(sentences)} sentences "
            f"in {time.time() - t:.2f}s"
        )

        if not sentences:
            logger.warning("ClaimExtraction: No sentences after preprocessing — aborting.")
            return

        # ── Stage 2 — Named Entity Recognition ──────────────────────────────────
        t = time.time()
        try:
            self.entity_recognizer.run(article, result, options, sentences)
        except Exception as e:
            logger.error(f"ClaimExtraction [Stage 2 NER] failed: {e}")
            raise
        logger.info(
            f"[Stage 2 | EntityRecognizer] {len(result.entities_in_article)} entities "
            f"in {time.time() - t:.2f}s"
        )

        # ── Stage 3 — Sentence Extraction + Deduplication ───────────────────────
        t = time.time()
        try:
            sentences = self.sentence_extractor.run(article, result, options, sentences)
        except Exception as e:
            logger.error(f"ClaimExtraction [Stage 3 SentenceExtraction] failed: {e}")
            raise
        logger.info(
            f"[Stage 3 | SentenceExtraction] {len(sentences)} kept "
            f"in {time.time() - t:.2f}s"
        )

        # ── Stage 4 — Decontextualization ────────────────────────────────────────
        t = time.time()
        try:
            sentences = self.decontextualizer.run(article, result, options, sentences)
        except Exception as e:
            logger.error(f"ClaimExtraction [Stage 4 Decontextualizer] failed: {e}")
            raise
        logger.info(f"[Stage 4 | Decontextualizer] complete in {time.time() - t:.2f}s")

        # ── Stage 5 — Check-Worthiness Scoring ──────────────────────────────────
        t = time.time()
        try:
            sentences = self.checkworthiness.run(article, result, options, sentences)
        except Exception as e:
            logger.error(f"ClaimExtraction [Stage 5 CheckWorthiness] failed: {e}")
            raise
        logger.info(f"[Stage 5 | CheckWorthiness] complete in {time.time() - t:.2f}s")

        # ── Stage 5.5 — Entity Mapping ───────────────────────────────────────────
        t = time.time()
        self._map_entities_to_sentences(sentences, result)
        logger.info(f"[Stage 5.5 | EntityMapping] complete in {time.time() - t:.2f}s")

        # ── Stage 6 — Sentence Embedding ─────────────────────────────────────────
        t = time.time()
        try:
            sentences = self.embedder.run(article, result, options, sentences)
        except Exception as e:
            logger.error(f"ClaimExtraction [Stage 6 Embedder] failed: {e}")
            raise
        logger.info(f"[Stage 6 | Embedder] complete in {time.time() - t:.2f}s")

        # ── Stage 7 — Sentence → Claim Conversion ────────────────────────────────
        # Anti-Regression: Claim stores source_sentence_indices (int ref) and the
        # decontextualised text, but NO raw/original text duplication.
        # Filter: only sentences that passed the check-worthiness threshold AND
        # meet options.min_confidence (default 0.75) are promoted to Claims.
        t = time.time()
        result.claims_in_article = [
            Claim(
                confidence=s.confidence,
                source_sentence_indices=[s.index],
                decontextualised_claim_text=s.text,
                decontextualised_claim_embedding=s.embedding,
                NER_entities=s.entities,
            )
            for s in sentences
            if s.is_checkworthy and s.confidence >= options.min_confidence
        ]
        logger.info(
            f"[Stage 7 | Sentence→Claim] {len(result.claims_in_article)} claims "
            f"in {time.time() - t:.2f}s"
        )

        # ── Stage 8 — Bias Detection (optional) ──────────────────────────────────
        if options.enable_bias_detection:
            t = time.time()
            try:
                self.bias_detector.run(article, result, options)
                logger.info(f"[Stage 8 | BiasDetector] complete in {time.time() - t:.2f}s")
            except Exception as e:
                logger.error(
                    f"[Stage 8 | BiasDetector] failed after {time.time() - t:.2f}s: {e}"
                )
                # Non-critical — do not re-raise; claims are already committed

        logger.info(
            f"--- ClaimExtraction Pipeline complete in "
            f"{time.time() - pipeline_start:.2f}s | "
            f"claims={len(result.claims_in_article)} "
            f"entities={len(result.entities_in_article)} ---"
        )
