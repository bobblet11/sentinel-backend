import logging
import spacy
from typing import List, Tuple

# Local imports
from microservices.nlp.models.base import SentenceProcessor
from common.models.api.redis_models import Article, NLPOptions, NLPResult, SentenceScore
from microservices.nlp.config import CW_THRESHOLD, CW_BATCH_SIZE

logger = logging.getLogger(__name__)


class CheckWorthiness(SentenceProcessor):
    """
    MODULAR CHECK-WORTHINESS LAYER

    Scores each sentence on its factual claim-worthiness using a lightweight
    rule-based feature model powered by spaCy's POS tagger and NER.

    Strategies Applied:
    1.  Entity Density Scoring: Sentences containing named entities (PERSON, ORG,
        GPE, EVENT, FAC, NORP) receive a +0.3 base score, with an additional +0.1
        for each extra entity beyond the first (max contribution from this rule: +0.4).
    2.  Numeric Content Bonus: Presence of numeric/quantitative entities (MONEY,
        PERCENT, CARDINAL, DATE, QUANTITY) contributes +0.4, as numerical claims are
        among the most check-worthy sentence types.
    3.  Reporting Verb Signal: Presence of reporting verbs (say, claim, state, report,
        announce, confirm, warn, accuse) contributes +0.1 — indicates attributed quotes.
    4.  Action Verb Signal: Presence of any non-reporting verb adds +0.1 — broad signal
        for event sentences.
    5.  Speculative Penalty: Any speculative modal or keyword (could, might, may, would,
        predict, expect, likely, possibly, perhaps, if, future, etc.) subtracts -0.5 to
        suppress forward-looking or opinion-based sentences.
    6.  Threshold: A sentence is marked is_checkworthy=True if its final clamped
        score >= 0.60.
    7.  Batching: Uses spaCy's nlp.pipe() for efficient batched processing
        (batch_size=32), avoiding per-sentence model reloads.

    Accepts and returns a local sentences list; does NOT write to result.
    """

    def __init__(self, nlp=None):
        if nlp is not None:
            logger.info("CheckWorthiness: Using shared spaCy model.")
            self.nlp = nlp
        else:
            logger.info("CheckWorthiness: Loading spaCy 'en_core_web_sm' model...")
            try:
                self.nlp = spacy.load("en_core_web_sm", disable=["lemmatizer"])
            except OSError:
                logger.error("CheckWorthiness: Run: python -m spacy download en_core_web_sm")
                raise

        self.reporting_verbs = {
            "say", "claim", "state", "report", "announce",
            "confirm", "warn", "accuse",
        }
        self.speculative_keywords = {
            "could", "might", "may", "would", "predict", "expect", "poised",
            "likely", "potential", "possibly", "perhaps", "if", "future",
        }

    def _score_doc(self, doc) -> Tuple[float, bool]:
        entities = [
            e for e in doc.ents
            if e.label_ in ("PERSON", "ORG", "GPE", "EVENT", "FAC", "NORP")
        ]
        numbers = [
            e for e in doc.ents
            if e.label_ in ("MONEY", "PERCENT", "CARDINAL", "DATE", "QUANTITY")
        ]

        verbs = [t for t in doc if t.pos_ == "VERB"]
        has_reporting  = any(v.lemma_.lower() in self.reporting_verbs  for v in verbs)
        has_action     = any(v.lemma_.lower() not in self.reporting_verbs for v in verbs)
        is_speculative = any(t.text.lower() in self.speculative_keywords for t in doc)

        score = 0.0
        if len(entities) >= 1: score += 0.3
        if len(entities) >= 2: score += 0.1
        if len(numbers)  >= 1: score += 0.4
        if has_reporting:       score += 0.1
        if has_action:          score += 0.1
        if is_speculative:      score -= 0.5

        score = max(0.0, min(1.0, score))
        return score, score >= CW_THRESHOLD

    def run(
        self,
        article: Article,
        result: NLPResult,
        options: NLPOptions,
        sentences: List[SentenceScore],
    ) -> List[SentenceScore]:
        """
        Scores each sentence for check-worthiness using rule-based NLP features.
        Populates confidence and is_checkworthy on each SentenceScore in-place.
        Returns the same list (modified in-place); does NOT write to result.
        """
        if not sentences:
            return []

        logger.info(
            f"CheckWorthiness: Evaluating {len(sentences)} sentences "
            f"(batch_size={CW_BATCH_SIZE}, threshold={CW_THRESHOLD})..."
        )

        texts = [s.text for s in sentences]
        for s_obj, doc in zip(sentences, self.nlp.pipe(texts, batch_size=CW_BATCH_SIZE)):
            score, is_checkworthy = self._score_doc(doc)
            s_obj.confidence     = float(score)
            s_obj.is_checkworthy = is_checkworthy

        worthy_count = sum(1 for s in sentences if s.is_checkworthy)
        logger.info(
            f"CheckWorthiness: {worthy_count}/{len(sentences)} sentences marked as check-worthy."
        )
        return sentences
