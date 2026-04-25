import logging
import time
from typing import List

import spacy

from common.models.api.dtos.job import JobStage
from common.models.api.redis_models import (
    Article,
    BiasProfile,
    Claim,
    NLPOptions,
    NLPResult,
    SentenceScore,
    StreamMessage,
)
from microservices.nlp.components.bias import BiasDetector
from microservices.nlp.components.checkworthy import CheckWorthinessFilter
from microservices.nlp.components.decontext import Decontextualizer
from microservices.nlp.components.device import DeviceConfig
from microservices.nlp.components.embedder import Embedder
from microservices.nlp.components.ner import EntityRecognizer

# Pipeline stage imports
from microservices.nlp.components.preprocess import Preprocessor
from microservices.nlp.components.sentenceextract import SentenceExtraction
from microservices.nlp.config import ENABLE_DECONTEXTUALIZATION

# Local imports
from microservices.nlp.models.base import ArticleProcessor

logger = logging.getLogger(__name__)


class ClaimExtraction(ArticleProcessor):
    """NLP Pipeline Orchestrator.

    Central hub that sequences 9 NLP stages in a deterministic, stateful pipeline:
      1. Preprocessor:         Clean & sentence-split text
      2. EntityRecognizer:     Extract entities (NER)
      3. SentenceExtraction:   Deduplicate & rank sentences
      4. Decontextualizer:     Rewrite sentences as self-contained (optional)
      5. CheckWorthinessFilter: Mark check-worthy claims
      5.5. Entity Mapping:      Link entities to sentences
      6. Embedder:             Generate 384-dim embeddings
      7. Sentence→Claim:       Commit claims to result
      8. BiasDetector:         Political/sentiment bias (optional)
      9. TopicClassifier:      Topic assignment (optional)

    Pipeline Contract:
        Input:  StreamMessage with Article
        Output: StreamMessage with NLPResult containing claims_in_article,
                entities_in_article, bias_profile, and topic_label

    This class owns the complete lifecycle of local List[SentenceScore].
    All writes to result.claims_in_article and result.entities_in_article
    are exclusively managed here. Individual components are lazily initialized
    or fetched from an optional ModelManager for centralized model lifecycle.
    """

    def __init__(self, device_config: DeviceConfig = None, model_manager=None):
        logger.info("ClaimExtraction: Initializing all pipeline stages...")
        t_start = time.time()

        if device_config is None:
            device_config = DeviceConfig.resolve(use_gpu=True)

        self.model_manager = model_manager

        # Load spaCy once and share across components that need it.
        # Keep NER enabled because CheckWorthinessFilter may rely on spaCy tokens.
        try:
            nlp_sm = spacy.load("en_core_web_sm", disable=["lemmatizer"])
        except OSError:
            logger.error(
                "spaCy model not found. Run: python -m spacy download en_core_web_sm"
            )
            raise

        self.preprocessor = Preprocessor(nlp=nlp_sm)
        self.entity_recognizer = EntityRecognizer(
            device_config=device_config, model_manager=model_manager
        )
        self.sentence_extractor = SentenceExtraction(device_config=device_config)
        self.decontextualizer = None
        if ENABLE_DECONTEXTUALIZATION:
            self.decontextualizer = Decontextualizer(
                device_config=device_config, nlp=nlp_sm, model_manager=model_manager
            )
        else:
            logger.info(
                "ClaimExtraction: Decontextualizer disabled via service configuration."
            )
        self.checkworthiness = CheckWorthinessFilter(device_config=device_config)
        self.embedder = Embedder(
            device_config=device_config, model_manager=model_manager
        )
        # Store args for lazy BiasDetector initialization (Stage 8)
        self._bias_device_config = device_config
        self._bias_model_manager = model_manager
        self._bias_detector = None

        # Store args for lazy TopicClassifier initialization (Stage 9)
        self._topic_device_config = device_config
        self._topic_model_manager = model_manager
        self._topic_classifier = None

        logger.info(
            "ClaimExtraction: All models ready in %.2fs.",
            time.time() - t_start,
        )

    def _map_entities_to_sentences(
        self,
        sentences: List[SentenceScore],
        result: NLPResult,
    ) -> None:
        """Link article-level entities to sentences via substring matching.

        For each sentence, finds all entities from result.entities_in_article
        that appear as substrings (case-insensitive) and assigns them.
        Modifies each SentenceScore.entities list in-place.

        Args:
            sentences: List of SentenceScore objects to annotate
            result: NLPResult containing entities_in_article to map
        """
        if not sentences or not result.entities_in_article:
            return
        for s_obj in sentences:
            s_obj.entities = [
                ent
                for ent in result.entities_in_article
                if ent.entity_text.lower() in s_obj.text.lower()
            ]

    def run(
        self, article: Article, message: StreamMessage, options: NLPOptions
    ) -> None:
        """Execute full NLP pipeline end-to-end.

        Orchestrates all 9 pipeline stages in order, logging timing and results
        at each stage. Writes final claims to result.claims_in_article (Stage 7),
        entities to result.entities_in_article (Stage 2), and optional
        bias_profile (Stage 8) and topic_label (Stage 9).

        Args:
            article: Article object containing text/summary and metadata
            message: StreamMessage to read initial payload and populate with NLPResult
            options: NLPOptions controlling decontextualization, bias detection, confidence thresholds

        Raises:
            Exception: Any stage failure logs and re-raises (critical path).
                       BiasDetector and TopicClassifier failures are non-critical
                       and fall back gracefully without stopping the pipeline.
        """
        pipeline_start = time.time()
        message.add_timestamp(JobStage.NLP_START)
        # ── Stage 1 — Preprocessing ──────────────────────────────────────────
        t = time.time()
        try:
            message.add_timestamp(JobStage.PREPROCESS_IN)
            sentences: List[SentenceScore] = self.preprocessor.run(
                article, message, options
            )
            message.add_timestamp(JobStage.PREPROCESS_OUT)
        except Exception as e:
            logger.error("ClaimExtraction [Stage 1 Preprocessor] failed: %s", e)
            raise
        logger.info(
            "[Stage 1 | Preprocessor] %d sentences in %.2fs",
            len(sentences),
            time.time() - t,
        )

        if not sentences:
            logger.warning(
                "ClaimExtraction: No sentences after preprocessing — aborting."
            )
            if not message.data.payload.bias_profile:
                message.data.payload.bias_profile = BiasProfile(
                    bias_category="Center",
                    bias_analysis_confidence=0.0,
                    sentiment_category="Neutral",
                    sentiment_analysis_confidence=0.0,
                )
            return

        # ── Stage 2 — Named Entity Recognition ──────────────────────────────
        t = time.time()
        try:
            message.add_timestamp(JobStage.NER_IN)
            self.entity_recognizer.run(article, message, options, sentences)
            message.add_timestamp(JobStage.NER_OUT)
        except Exception as e:
            logger.error("ClaimExtraction [Stage 2 NER] failed: %s", e)
            raise
        logger.info(
            "[Stage 2 | EntityRecognizer] %d entities in %.2fs",
            len(message.create_nlp_result().entities_in_article),
            time.time() - t,
        )

        # ── Stage 3 — Sentence Extraction + Deduplication ───────────────────
        t = time.time()
        try:
            message.add_timestamp(JobStage.SENT_EXTRACTION_IN)
            sentences = self.sentence_extractor.run(
                article, message, options, sentences
            )
            message.add_timestamp(JobStage.SENT_EXTRACTION_OUT)
        except Exception as e:
            logger.error("ClaimExtraction [Stage 3 SentenceExtraction] failed: %s", e)
            raise
        logger.info(
            "[Stage 3 | SentenceExtraction] %d kept in %.2fs",
            len(sentences),
            time.time() - t,
        )

        # ── Stage 4 — Decontextualization ────────────────────────────────────
        t = time.time()
        message.add_timestamp(JobStage.DECONTEXT_IN)
        if options.enable_decontextualization and self.decontextualizer is not None:
            try:
                sentences = self.decontextualizer.run(
                    article, message, options, sentences
                )
            except Exception as e:
                logger.error("ClaimExtraction [Stage 4 Decontextualizer] failed: %s", e)
                raise
            logger.info(
                "[Stage 4 | Decontextualizer] complete in %.2fs", time.time() - t
            )
        elif options.enable_decontextualization:
            logger.info(
                "[Stage 4 | Decontextualizer] skipped (disabled by service config)"
            )
        else:
            logger.info("[Stage 4 | Decontextualizer] skipped (disabled in options)")

        message.add_timestamp(JobStage.DECONTEXT_OUT)

        # ── Stage 5 — Check-Worthiness Scoring ──────────────────────────────
        t = time.time()
        try:
            message.add_timestamp(JobStage.CHECK_WORTHY_IN)
            sentences = self.checkworthiness.run(article, message, options, sentences)
            # Clear claims built by CheckWorthinessFilter; Stage 7 rebuilds them
            # after embeddings and entity mapping are complete.
            message.data.payload.claims_in_article = []
            message.add_timestamp(JobStage.CHECK_WORTHY_OUT)
        except Exception as e:
            logger.error("ClaimExtraction [Stage 5 CheckWorthiness] failed: %s", e)
            raise
        logger.info("[Stage 5 | CheckWorthiness] complete in %.2fs", time.time() - t)

        # ── Stage 5.5 — Entity Mapping ───────────────────────────────────────
        t = time.time()
        message.add_timestamp(JobStage.CHECK_WORTHY_ENTITY_MAPPING_IN)
        result = message.create_nlp_result()
        self._map_entities_to_sentences(sentences, result)
        message.set_nlp_result(result)
        logger.info("[Stage 5.5 | EntityMapping] complete in %.2fs", time.time() - t)
        message.add_timestamp(JobStage.CHECK_WORTHY_ENTITY_MAPPING_OUT)

        # ── Stage 6 — Sentence Embedding ─────────────────────────────────────
        t = time.time()
        try:
            message.add_timestamp(JobStage.SENTENCE_EMBED_IN)
            sentences = self.embedder.run(article, message, options, sentences)
            message.add_timestamp(JobStage.SENTENCE_EMBED_OUT)
        except Exception as e:
            logger.error("ClaimExtraction [Stage 6 Embedder] failed: %s", e)
            raise
        logger.info("[Stage 6 | Embedder] complete in %.2fs", time.time() - t)

        # ── Stage 7 — Sentence → Claim Conversion ────────────────────────────
        t = time.time()
        message.add_timestamp(JobStage.CONVERT_TO_CLAIM_IN)
        selected_sentences = [
            s
            for s in sentences
            if s.is_checkworthy and s.confidence >= options.min_confidence
        ]

        if not selected_sentences and sentences:
            fallback_limit = max(1, min(options.max_claims, len(sentences)))
            selected_sentences = sorted(
                sentences,
                key=lambda s: s.confidence,
                reverse=True,
            )[:fallback_limit]
            logger.warning(
                "[Stage 7 | Sentence→Claim] No sentences passed check-worthiness; "
                "using fallback top-%d sentences by confidence.",
                fallback_limit,
            )

        # Write directly to payload — set_nlp_result won't overwrite a non-empty list.
        message.data.payload.claims_in_article = [
            Claim(
                confidence=s.confidence,
                source_sentence_indices=[s.index],
                decontextualised_claim_text=s.text,
                decontextualised_claim_embedding=s.embedding,
                NER_entities=s.entities,
            )
            for s in selected_sentences
        ]
        logger.info(
            "[Stage 7 | Sentence→Claim] %d claims in %.2fs",
            len(message.data.payload.claims_in_article),
            time.time() - t,
        )
        message.add_timestamp(JobStage.CONVERT_TO_CLAIM_OUT)

        # ── Stage 8 — Bias Detection (optional) ──────────────────────────────
        if options.enable_bias_detection:
            if self._bias_detector is None:
                self._bias_detector = BiasDetector(
                    device_config=self._bias_device_config,
                    model_manager=self._bias_model_manager,
                )
            t = time.time()
            try:
                message.add_timestamp(JobStage.BIAS_ANAL_IN)
                self._bias_detector.run(article, message, options)
                logger.info(
                    "[Stage 8 | BiasDetector] complete in %.2fs", time.time() - t
                )
                message.add_timestamp(JobStage.BIAS_ANAL_OUT)
            except Exception as e:
                logger.error(
                    "[Stage 8 | BiasDetector] failed after %.2fs: %s",
                    time.time() - t,
                    e,
                )
                # Non-critical — do not re-raise; claims are already committed.
                # Write a neutral fallback so downstream never sees None.
                if not message.data.payload.bias_profile:
                    message.data.payload.bias_profile = BiasProfile(
                        bias_category="Center",
                        bias_analysis_confidence=0.0,
                        sentiment_category="Neutral",
                        sentiment_analysis_confidence=0.0,
                    )

        # ── Stage 9 — Topic Classification ───────────────────────────────────
        t = time.time()
        try:
            if self._topic_classifier is None:
                from microservices.nlp.components.topic_classifier import (
                    TopicClassifier,
                )

                self._topic_classifier = TopicClassifier(
                    device_config=self._topic_device_config,
                    model_manager=self._topic_model_manager,
                )
            self._topic_classifier.run(article, message, options)
        except Exception as e:
            logger.warning("ClaimExtraction [Stage 9 TopicClassifier] failed: %s", e)
        logger.info("[Stage 9 | TopicClassifier] complete in %.2fs", time.time() - t)

        # Expose processed sentences so set_nlp_result() can copy them
        # to the MessagePayload for downstream services.
        # result = message.create_nlp_result()
        # result.sentences = sentences
        # message.set_nlp_result(result)

        logger.info(
            "--- ClaimExtraction Pipeline complete in %.2fs | "
            "claims=%d entities=%d ---",
            time.time() - pipeline_start,
            len(message.data.payload.claims_in_article),
            len(message.data.payload.entities_in_article),
        )

        message.add_timestamp(JobStage.NLP_END)
