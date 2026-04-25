import logging
import re
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from common.models.api.redis_models import Article, NLPOptions, NLPResult, StreamMessage
from microservices.nlp.components.device import DeviceConfig
from microservices.nlp.config import TOPIC_LABELS, TOPIC_SIMILARITY_THRESHOLD
from microservices.nlp.models.base import ArticleProcessor

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Topic description corpus — one rich paragraph per topic.
# Written as natural language sentences so all-mpnet-base-v2 can encode them
# coherently.  "General" is excluded: it is assigned via the threshold fallback,
# not by competing against other topics.
# ---------------------------------------------------------------------------
_TOPIC_DESCRIPTIONS: Dict[str, str] = {
    "Politics": (
        "Politicians debated new legislation in parliament and congress. "
        "The president signed an executive order affecting government policy. "
        "Voters headed to the polls in the national election. "
        "The prime minister announced a major cabinet reshuffle. "
        "A federal court ruling challenged the administration's legal authority. "
        "The senator faced calls to resign following the ethics investigation. "
        "Political parties launched their campaign platforms ahead of the vote."
    ),
    "World": (
        "International diplomats met at the United Nations to discuss the ongoing conflict. "
        "Military forces clashed along the disputed border region. "
        "An airman was rescued after his jet was shot down during the military operation. "
        "Refugees fleeing the humanitarian crisis sought asylum in neighbouring countries. "
        "Foreign ministers held emergency talks over rising geopolitical tensions. "
        "Troops were deployed to support peacekeeping efforts in the conflict zone. "
        "The war has caused widespread civilian casualties and displacement."
    ),
    "Technology": (
        "The tech startup launched a new artificial intelligence product at the conference. "
        "Researchers published a breakthrough in machine learning and deep neural networks. "
        "A major cybersecurity breach exposed millions of user accounts and leaked private data. "
        "Apple and Google announced new software and hardware features for their devices. "
        "The semiconductor company unveiled its next-generation chip architecture. "
        "The robotics company demonstrated its latest autonomous vehicle system."
    ),
    "Health": (
        "Doctors reported a rise in cases of the infectious disease across the region. "
        "The clinical trial showed promising results for the new cancer treatment. "
        "Public health officials warned about the spread of the virus. "
        "The hospital introduced a new surgical procedure for cardiac patients. "
        "Mental health services are struggling to meet growing demand. "
        "A product recall was issued after contamination risks were identified."
    ),
    "Science": (
        "Scientists discovered a new species in the depths of the Amazon rainforest. "
        "The space agency launched a probe to study the surface of Mars. "
        "Climate researchers warned that global temperatures are rising faster than predicted. "
        "The study published in Nature revealed new insights into human evolution. "
        "Astronomers detected a rare cosmic phenomenon using the James Webb telescope. "
        "Geologists mapped a previously unknown fault line beneath the ocean floor."
    ),
    "Business": (
        "The company reported record quarterly earnings, beating market expectations. "
        "Central banks raised interest rates to combat rising inflation. "
        "Stock markets fell sharply after the trade war escalated. "
        "The merger between the two corporations was approved by regulators. "
        "Unemployment figures rose as the economy slowed and businesses cut jobs. "
        "The retail chain announced it would close dozens of stores nationwide."
    ),
    "Entertainment": (
        "The film won three Academy Awards at the Hollywood ceremony. "
        "The pop star's new album debuted at number one on the charts. "
        "The streaming service announced a major new television series. "
        "Critics praised the director's latest movie at the film festival. "
        "The celebrity couple announced their divorce in a joint statement. "
        "The band cancelled their world tour citing creative differences."
    ),
    "Sports": (
        "The team won the championship after a dramatic final match. "
        "The footballer scored a hat-trick to lead his side to victory. "
        "The Olympic athlete broke the world record in the 100-metre sprint. "
        "The coach was sacked after a string of poor results this season. "
        "The tennis player defeated the top seed to reach the grand slam final. "
        "The rugby side clinched promotion with a last-minute try. "
        "The premier league club announced a new signing from the transfer window. "
        "The cricket team dominated the test series with an emphatic innings victory."
    ),
}

# Topic labels that have descriptions (excludes "General" — assigned via threshold).
_CLASSIFIED_TOPICS: List[str] = [t for t in TOPIC_LABELS if t != "General"]

# Digest/bulletin title patterns — these articles carry no topic signal and
# land unpredictably near centroids.  An empty doc forces "General".
_DIGEST_PATTERNS: Tuple[str, ...] = (
    r"^latest news bulletin\b",
    r"^(morning|afternoon|evening) (mail|update|briefing|bulletin)\b",
    r"^(today('s)?|tonight('s)?) (top )?headlines?\b",
    r"^news (roundup|wrap|digest)\b",
)


_BYLINE_RE = re.compile(
    r"\s*[-|]\s*(BBC|CBC|ABC|CBS|NBC|NPR|Reuters|AP|CNN)[^\n]*$",
    re.IGNORECASE,
)
_PRIVACY_TRIGGERS = (
    "cookie",
    "browsing",
    "consent",
    "privacy policy",
    "copy/paste the link",
)


def _build_doc(article: Article, result: NLPResult) -> str:
    """Construct a document string from title + top-4 claims by confidence."""
    title = (article.title or "").strip()

    top_claims: List[str] = []
    if result.claims_in_article:
        sorted_claims = sorted(
            result.claims_in_article,
            key=lambda c: (c.confidence or 0.0),
            reverse=True,
        )
        top_claims = [
            c.decontextualised_claim_text
            for c in sorted_claims[:4]
            if c.decontextualised_claim_text
        ]

    doc = (title + (" " + " ".join(top_claims) if top_claims else "")).strip()[:600]

    # Strip trailing source bylines.
    doc = _BYLINE_RE.sub("", doc)

    # Strip cookie/privacy boilerplate from scraped video pages.
    if any(t in doc.lower() for t in _PRIVACY_TRIGGERS):
        first_sent = re.split(r"(?<=[.!?])\s", doc)[0]
        doc = first_sent[:120]

    # Blank digest/bulletin titles — they have no discriminative topic signal.
    if any(re.search(p, doc.lower()) for p in _DIGEST_PATTERNS):
        return ""

    return doc.strip()


class TopicClassifier(ArticleProcessor):
    """
    Stage 9 — Topic Classification.

    Assigns each article to one of the 8 predefined topic categories
    (Politics, World, Technology, Health, Science, Business, Entertainment,
    Sports) or falls back to "General" when no topic scores above
    TOPIC_SIMILARITY_THRESHOLD.

    Implementation:
    - Reuses the SentenceTransformer already loaded by the Embedder
      (retrieved from ModelManager key "EMBEDDING") — no additional model
      download or memory cost.
    - Pre-computes L2-normalised topic description embeddings once at init;
      inference is a single dot-product per article.
    - Writes topic_label + topic_confidence to the StreamMessage payload via
      set_nlp_result().  Non-fatal — any exception is logged and the pipeline
      continues with topic_label=None.
    """

    def __init__(
        self,
        device_config: DeviceConfig,
        model_manager: Optional[Any] = None,
    ) -> None:
        logger.info("TopicClassifier: Initializing...")

        self.model = None
        try:
            if model_manager is not None:
                from common.model_manager.registry import ModelState

                if model_manager.get_state("EMBEDDING") == ModelState.READY:
                    self.model = model_manager.get("EMBEDDING")
                    logger.info(
                        "TopicClassifier: Using EMBEDDING model from ModelManager."
                    )
                else:
                    logger.warning(
                        "TopicClassifier: EMBEDDING model not ready (%s) — "
                        "topic classification will be skipped.",
                        model_manager.get_state("EMBEDDING").value,
                    )
                    return

            if self.model is None:
                # Fallback: load directly (should not normally be needed).
                from sentence_transformers import SentenceTransformer

                from microservices.nlp.config import EMBEDDING_MODEL

                self.model = SentenceTransformer(
                    EMBEDDING_MODEL, device=device_config.device
                )
                logger.info("TopicClassifier: Loaded EMBEDDING model directly.")

            # Pre-compute normalised topic description embeddings: shape (n_topics, 768).
            description_texts = [_TOPIC_DESCRIPTIONS[t] for t in _CLASSIFIED_TOPICS]
            self._topic_embs: np.ndarray = self.model.encode(
                description_texts,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            logger.info(
                "TopicClassifier: Ready — %d topics, threshold=%.2f.",
                len(_CLASSIFIED_TOPICS),
                TOPIC_SIMILARITY_THRESHOLD,
            )
        except Exception as e:
            logger.error("TopicClassifier: Initialization failed: %s", e)
            self.model = None

    def run(
        self,
        article: Article,
        message: StreamMessage,
        options: NLPOptions,
    ) -> None:
        """
        Classifies the article's topic and writes the result to the message payload.
        Silently skips (topic stays None) if the model is unavailable.
        """
        if self.model is None:
            logger.warning("TopicClassifier: Model unavailable — skipping.")
            return

        result = message.create_nlp_result()
        doc = _build_doc(article, result)

        if not doc:
            result.topic_label = "General"
            result.topic_confidence = 0.0
            message.set_nlp_result(result)
            return

        doc_emb: np.ndarray = self.model.encode(
            [doc], normalize_embeddings=True, show_progress_bar=False
        )[0]

        sims: np.ndarray = doc_emb @ self._topic_embs.T
        best_idx = int(np.argmax(sims))
        best_score = float(sims[best_idx])

        if best_score < TOPIC_SIMILARITY_THRESHOLD:
            result.topic_label = "General"
            result.topic_confidence = best_score
        else:
            result.topic_label = _CLASSIFIED_TOPICS[best_idx]
            result.topic_confidence = best_score

        message.set_nlp_result(result)
        logger.debug(
            "TopicClassifier: '%s' → %s (%.3f)",
            (article.title or "")[:60],
            result.topic_label,
            result.topic_confidence,
        )
