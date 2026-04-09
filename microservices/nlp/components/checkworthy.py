import logging
from typing import Any, List, Optional

# Local imports
from microservices.nlp.models.base import SentenceProcessor
from microservices.nlp.components.device import DeviceConfig
from common.models.api.redis_models import Article, NLPOptions, NLPResult, Claim, SentenceScore
from microservices.nlp.config import (
    CHECKWORTHY_BATCH_SIZE,
    CHECKWORTHY_MODEL,
    MAX_SENTENCES_FOR_CHECKWORTHY,
)

logger = logging.getLogger(__name__)

class CheckWorthinessFilter(SentenceProcessor):
    """
    Filters sentences to identify factual claims worth checking.
    Uses text classification (ClaimBuster-DeBERTaV2) to categorize sentences.

    Model: whispAI/ClaimBuster-DeBERTaV2
    Labels: NFS (Non-Factual) / UFS (Unimportant Factual) / CFS (Check-worthy Factual)
    
    Now implements SentenceProcessor: accepts sentences list as parameter,
    modifies is_checkworthy/claim_type/confidence in-place, stores claims in result,
    and returns the sentence list.
    """

    def __init__(
        self,
        device_config: Optional[DeviceConfig] = None,
        classifier: Any = None,
        threshold: float = 0.50,
    ):
        """
        Args:
            device_config: Unified device configuration (unused directly — model
                           is loaded via ModelManager which owns device placement).
            classifier: Loaded pipeline("text-classification")
            threshold: Minimum CFS score to mark a sentence as check-worthy
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

    def run(self, article: Article, result: NLPResult, options: NLPOptions, sentences: List[SentenceScore]) -> List[SentenceScore]:
        """
        Classifies each sentence in the provided list.
        Adds 'is_checkworthy', 'claim_type', and 'confidence' attributes to each sentence.
        Stores check-worthy sentences as claims in result.claims_in_article.
        Returns the same sentence list (possibly filtered or modified).
        """
        if not sentences:
            return sentences

        candidate_indices = list(range(len(sentences)))

        # Bound expensive zero-shot work by selecting top-central sentences first.
        if len(candidate_indices) > MAX_SENTENCES_FOR_CHECKWORTHY:
            ranked = sorted(
                candidate_indices,
                key=lambda idx: sentences[idx].score if sentences[idx].score is not None else 0.0,
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
            result.claims_in_article = claims_discovered
            logger.info(f"CheckWorthiness: Identified {count} factual claims out of {len(texts)} sentences.")

        except Exception as e:
            logger.error(f"CheckWorthiness analysis failed: {e}")
            # Fail gracefully: assume nothing is checkworthy so we don't crash
            for s in sentences:
                s.is_checkworthy = False
        
        return sentences
