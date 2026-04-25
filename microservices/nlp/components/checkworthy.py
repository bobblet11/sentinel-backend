import logging
from typing import Any, List, Optional

from common.models.api.redis_models import (
    Article,
    Claim,
    NLPOptions,
    SentenceScore,
    StreamMessage,
)
from microservices.nlp.components.device import DeviceConfig
from microservices.nlp.config import (
    CHECKWORTHY_BATCH_SIZE,
    MAX_SENTENCES_FOR_CHECKWORTHY,
)

# Local imports
from microservices.nlp.models.base import SentenceProcessor

logger = logging.getLogger(__name__)


class CheckWorthinessFilter(SentenceProcessor):
    """Check-Worthiness Filter for Fact-Check Candidate Detection.

    Filters sentences to identify factual claims that warrant fact-checking.
    Uses a text classification model trained on claim check-worthiness.

    Model Details:
        - Model: whispAI/ClaimBuster-DeBERTaV2
        - Framework: DeBERTaV2 (enhanced BERT variant)
        - Output Classes: 3 labels
            - NFS: Non-Factual Statement
            - UFS: Unimportant Factual Statement
            - CFS: Check-worthy Factual Statement (target)
        - Confidence: Continuous score [0.0, 1.0] for CFS probability
        - Default Threshold: 0.50 (configurable)

    Filtering Strategy:
        1. Ranks all sentences by centrality score (from SentenceExtraction)
        2. Limits inference to top MAX_SENTENCES_FOR_CHECKWORTHY candidates
        3. Classifies each selected sentence
        4. Marks is_checkworthy=True if CFS score >= threshold
        5. Later stages filter on is_checkworthy and confidence thresholds

    Contract:
        Input:  List[SentenceScore] with text, score, entities
        Output: Same list with is_checkworthy, claim_type, confidence populated
                (in-place); also stores claims in result.claims_in_article
    """

    def __init__(
        self,
        device_config: Optional[DeviceConfig] = None,
        classifier: Any = None,
        threshold: float = 0.50,
    ):
        """Initialize check-worthiness classifier.

        Args:
            device_config: Device configuration (unused; classifier device
                          managed by ModelManager)
            classifier: Pre-loaded text-classification pipeline (optional)
            threshold: Minimum CFS confidence to mark sentence as check-worthy
        """
        self.classifier = classifier
        self.threshold = threshold

        # Load model if not provided
        if not self.classifier:
            from microservices.nlp.config import model_manager

            try:
                self.classifier = model_manager.get("CHECKWORTHY")
            except Exception as e:
                self.classifier = None
                logger.warning(
                    "CheckWorthiness: CHECKWORTHY model unavailable (%s). "
                    "Continuing in degraded mode.",
                    e,
                )

    def run(
        self,
        article: Article,
        message: StreamMessage,
        options: NLPOptions,
        sentences: List[SentenceScore],
    ) -> List[SentenceScore]:
        """Classify and filter sentences by check-worthiness.

        Performs batch inference on top-ranked sentences. For each classified
        sentence, populates is_checkworthy (CFS score >= threshold), claim_type,
        and confidence. Stores check-worthy sentences as Claim objects in
        result.claims_in_article for later filtering by min_confidence threshold.

        Args:
            article: Article object (for logging)
            message: StreamMessage to populate claims
            options: NLPOptions (for logging)
            sentences: List[SentenceScore] with text, score, entities; modified in-place

        Returns:
            Same sentence list with is_checkworthy, claim_type, confidence fields set

        Side Effects:
            Updates message.data.payload.claims_in_article with check-worthy claims.
            If classifier unavailable, all sentences marked is_checkworthy=False
            and pipeline continues gracefully.
        """
        if not sentences:
            return sentences

        candidate_indices = list(range(len(sentences)))

        # Bound expensive zero-shot work by selecting top-central sentences first.
        if len(candidate_indices) > MAX_SENTENCES_FOR_CHECKWORTHY:
            ranked = sorted(
                candidate_indices,
                key=lambda idx: (
                    sentences[idx].score if sentences[idx].score is not None else 0.0
                ),
                reverse=True,
            )
            candidate_indices = ranked[:MAX_SENTENCES_FOR_CHECKWORTHY]

        logger.info(
            "CheckWorthiness: Analyzing %s/%s sentences...",
            len(candidate_indices),
            len(sentences),
        )

        # Run model only on selected candidates.
        texts = [sentences[i].text for i in candidate_indices]

        if self.classifier is None:
            logger.warning(
                "CheckWorthiness: classifier unavailable; marking all sentences as not checkworthy."
            )
            for s in sentences:
                s.is_checkworthy = False
                s.confidence = 0.0
            return sentences

        try:
            # Run Inference (Batch)
            predictions = self.classifier(
                texts,
                truncation=True,
                max_length=512,
                batch_size=CHECKWORTHY_BATCH_SIZE,
            )

            count = 0
            claims_discovered = []

            for local_idx, label_scores in enumerate(predictions):
                i = candidate_indices[local_idx]
                top_label = max(label_scores, key=lambda x: x["score"])["label"]
                # Labels may be full strings e.g. "Check-worthy Factual Statement (CFS)"
                cfs_score = next(
                    (item["score"] for item in label_scores if "CFS" in item["label"]),
                    0.0,
                )

                is_worthy = cfs_score >= self.threshold

                sentences[i].is_checkworthy = is_worthy
                sentences[i].claim_type = top_label
                sentences[i].confidence = cfs_score

                if is_worthy:
                    count += 1

                    # Construct and store the Claim object
                    claim_obj = Claim(
                        confidence=cfs_score,
                        source_sentence_indices=[i],
                        decontextualised_claim_text=sentences[i].text,
                        decontextualised_claim_embedding=sentences[i].embedding,
                        NER_entities=sentences[i].entities,
                    )
                    claims_discovered.append(claim_obj)

            # Update the result object
            result = message.create_nlp_result()
            result.claims_in_article = claims_discovered
            message.set_nlp_result(result)
            logger.info(
                f"CheckWorthiness: Identified {count} factual claims out of {len(texts)} sentences."
            )

        except Exception as e:
            logger.error(f"CheckWorthiness analysis failed: {e}")
            # Fail gracefully: assume nothing is checkworthy so we don't crash
            for s in sentences:
                s.is_checkworthy = False

        return sentences
