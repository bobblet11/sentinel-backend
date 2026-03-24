import logging
from typing import Any, List

# Local imports
from microservices.nlp.models.base import NLPComponent
from common.models.api.redis_models import Article, NLPOptions, NLPResult, Claim
from microservices.nlp.config import (
    CHECKWORTHY_BATCH_SIZE,
    CHECKWORTHY_MODEL,
    MAX_SENTENCES_FOR_CHECKWORTHY,
)

logger = logging.getLogger(__name__)

class CheckWorthinessFilter(NLPComponent):
    """
    Filters sentences to identify factual claims worth checking.
    Uses Zero-Shot Classification (BART-MNLI) to categorize sentences.
    
    Model: facebook/bart-large-mnli
    Candidates: ["factual claim", "opinion", "spam", "question"]
    """
    def __init__(self, classifier: Any = None):
        """
        Args:
            classifier: Loaded pipeline("zero-shot-classification")
        """
        self.classifier = classifier
        self.candidate_labels = ["fact", "opinion"]
        # Threshold: Lowered to capture descriptive news reporting
        self.threshold = 0.50

        # Load model if not provided
        if not self.classifier:
            from microservices.nlp.config import model_manager

            self.classifier = model_manager.get("CHECKWORTHY")

    def run(self, article: Article, result: NLPResult, options: NLPOptions) -> None:
        """
        Classifies each sentence in result.sentences.
        Adds 'is_checkworthy', 'claim_type', and 'confidence' attributes to the sentence objects.
        """
        if not result.sentences:
            return

        sentences = result.sentences
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

        try:
            # Run Inference (Batch)
            predictions = self.classifier(
                texts,
                self.candidate_labels,
                multi_label=False,
                batch_size=CHECKWORTHY_BATCH_SIZE,
                # Removed hypothesis_template to use the default "This example is {}." which is often more robust for simple labels.
            )

            count = 0
            claims_discovered = []
            
            for local_idx, pred in enumerate(predictions):
                i = candidate_indices[local_idx]
                # pred format: 
                # {'sequence': '...', 'labels': ['fact', 'opinion'], 'scores': [0.85, 0.15]}
                
                top_label = pred['labels'][0]
                top_score = pred['scores'][0]

                # Determine checkworthiness
                is_worthy = (top_label == "fact" and top_score >= self.threshold)

                # Assign attributes to the Sentence object
                # NOTE: Ensure schemas.py is updated to support these fields (Task B.2)
                result.sentences[i].is_checkworthy = is_worthy
                result.sentences[i].claim_type = top_label
                result.sentences[i].confidence = top_score

                if is_worthy:
                    count += 1
                    
                    # Construct and store the Claim object
                    claim_obj = Claim(
                        confidence=top_score,
                        source_sentence_indices=[i],
                        contextualised_claim_text=result.sentences[i].text,
                        decontextualised_claim_text=result.sentences[i].text, # Assuming text is already processed/clean
                        decontextualised_claim_embedding=result.sentences[i].embedding,
                        NER_entities=result.sentences[i].entities
                    )
                    claims_discovered.append(claim_obj)
                    
                    # logger.debug(f"Claim: {texts[i][:50]}... ({top_score:.2f})")

            # Update the result object
            result.claims_in_article = claims_discovered
            logger.info(f"CheckWorthiness: Identified {count} factual claims out of {len(texts)} sentences.")

        except Exception as e:
            logger.error(f"CheckWorthiness analysis failed: {e}")
            # Fail gracefully: assume nothing is checkworthy so we don't crash
            for s in result.sentences:
                s.is_checkworthy = False
