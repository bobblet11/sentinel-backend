import logging
from typing import Any, Optional

from transformers import pipeline

from common.models.api.redis_models import (
    Article,
    BiasProfile,
    NLPOptions,
    StreamMessage,
)
from microservices.nlp.components.device import DeviceConfig
from microservices.nlp.config import (
    BIAS_MAX_CHARS,
    BIAS_POLITICAL_MODEL,
    BIAS_SENTIMENT_MAX_LEN,
    BIAS_SENTIMENT_MODEL,
)

# Local imports
from microservices.nlp.models.base import ArticleProcessor

logger = logging.getLogger(__name__)


class BiasDetector(ArticleProcessor):
    """Article-Level Political Bias and Tone Classifier.

    Performs two-stage analysis on article text:
    1. Political Bias: Left/Center/Right classification
    2. Emotional Tone: Negative/Neutral/Positive sentiment

    Model Details:
        Political Model: premsa/political-bias-prediction-allsides-BERT
            - Fine-tuned on AllSides-rated news articles (F1=0.904)
            - Labels: LABEL_0=Left, LABEL_1=Center, LABEL_2=Right
            - Optimized for political lean detection

        Sentiment Model: cardiffnlp/twitter-roberta-base-sentiment-latest
            - RoBERTa model trained on Twitter text
            - Outputs: negative, neutral, positive
            - Maps to human-readable tone strings

    Processing:
        - Input text truncated to BIAS_MAX_CHARS (default 2000) for speed
        - Inference time < 1s on CPU for most articles
        - FP16 support on CUDA for memory efficiency
        - Graceful degradation: failures fall back to neutral profile

    Contract:
        Input:  Article with text or summary
        Output: result.bias_profile with bias_category, bias_analysis_confidence,
                sentiment_category, sentiment_analysis_confidence
    """

    # premsa/political-bias-prediction-allsides-BERT label mapping
    # Dataset label order: 0=Left, 1=Center, 2=Right
    _LABEL_MAP = {
        "LABEL_0": "Left",
        "LABEL_1": "Center",
        "LABEL_2": "Right",
    }
    _TONE_MAP = {
        "negative": "Negative",
        "neutral": "Neutral",
        "positive": "Positive",
    }

    def __init__(
        self, device_config: DeviceConfig, model_manager: Optional[Any] = None
    ):
        logger.info(
            f"BiasDetector: Loading models on {device_config.device.upper()} "
            f"(fp16={device_config.use_fp16})..."
        )

        try:
            if model_manager is not None:
                from common.model_manager.registry import ModelState

                pol_ok = model_manager.get_state("BIAS_POLITICAL") == ModelState.READY
                sent_ok = model_manager.get_state("BIAS_SENTIMENT") == ModelState.READY
                if pol_ok and sent_ok:
                    self.political_classifier = model_manager.get("BIAS_POLITICAL")
                    self.sentiment_analyzer = model_manager.get("BIAS_SENTIMENT")
                    logger.info("BiasDetector: Using pipelines from ModelManager.")
                    return
                else:
                    logger.warning(
                        "BiasDetector: ModelManager states — political=%s, sentiment=%s. "
                        "Falling back to direct load.",
                        model_manager.get_state("BIAS_POLITICAL").value,
                        model_manager.get_state("BIAS_SENTIMENT").value,
                    )

            _dtype_kwargs = (
                {"dtype": device_config.dtype} if device_config.use_fp16 else {}
            )
            self.political_classifier = pipeline(
                "text-classification",
                model=BIAS_POLITICAL_MODEL,
                device=device_config.device_id,
                top_k=None,
                truncation=True,
                max_length=512,
                **_dtype_kwargs,
            )
            self.sentiment_analyzer = pipeline(
                "sentiment-analysis",
                model=BIAS_SENTIMENT_MODEL,
                device=device_config.device_id,
                truncation=True,
                max_length=BIAS_SENTIMENT_MAX_LEN,
                **_dtype_kwargs,
            )
            logger.info("BiasDetector: Models loaded successfully.")
        except Exception as e:
            logger.error(f"BiasDetector: Failed to load models: {e}")
            raise

    def _neutral_profile(self) -> BiasProfile:
        """Return zero-confidence neutral profile for graceful degradation.

        Returns:
            BiasProfile with Center bias, Neutral sentiment, confidence 0.0
        """
        return BiasProfile(
            bias_category="Center",
            bias_analysis_confidence=0.0,
            sentiment_category="Neutral",
            sentiment_analysis_confidence=0.0,
        )

    def run(
        self, article: Article, message: StreamMessage, options: NLPOptions
    ) -> None:
        """Classify article political bias and emotional tone.

        Performs two-stage classification on article text (truncated to
        BIAS_MAX_CHARS). Updates result.bias_profile with political lean
        (Left/Center/Right) and emotional tone (Negative/Neutral/Positive)
        along with confidence scores.

        Args:
            article: Article with text or summary to analyze
            message: StreamMessage to read/write bias result
            options: NLPOptions (for logging context)

        Returns:
            None (writes directly to message via set_nlp_result)

        Side Effects:
            Updates message.data.payload.bias_profile. On failure, stores
            neutral profile with confidence 0.0 and logs error (non-critical).
        """
        text = (article.text or article.summary or "").strip()
        if not text:
            logger.warning("BiasDetector: No text available — using neutral profile.")
            result = message.create_nlp_result()
            result.bias_profile = self._neutral_profile()
            message.set_nlp_result(result)
            return

        result = message.create_nlp_result()
        analysis_text = text[:BIAS_MAX_CHARS]

        # ── Political Bias ──────────────────────────────────────────────────────
        try:
            bias_out_raw = self.political_classifier(analysis_text)
            # top_k=None returns [[{label, score}, ...]] for a single string — unwrap batch dim
            bias_out: list = (
                bias_out_raw[0]
                if bias_out_raw and isinstance(bias_out_raw[0], list)
                else bias_out_raw
            )
            # Sort descending by score to get top prediction first
            bias_out = sorted(bias_out, key=lambda x: x["score"], reverse=True)
            raw_label = bias_out[0]["label"]
            confidence = float(bias_out[0]["score"])
            # scores: Dict[str, float] = {
            #     self._LABEL_MAP.get(item["label"], "Center"): float(item["score"])
            #     for item in bias_out
            # }
            political_bias = self._LABEL_MAP.get(raw_label, "Center")

        except Exception as e:
            logger.error(f"BiasDetector: Political bias classification failed: {e}")
            result.bias_profile = self._neutral_profile()
            message.set_nlp_result(result)
            return

        # ── Emotional Tone ──────────────────────────────────────────────────────
        emotional_tone: Optional[str] = None
        tone_out = None
        try:
            tone_out = self.sentiment_analyzer(analysis_text[:512])
            raw_tone = tone_out[0]["label"].lower() if tone_out else "neutral"
            emotional_tone = self._TONE_MAP.get(raw_tone, raw_tone.capitalize())
        except Exception as e:
            logger.warning(f"BiasDetector: Tone analysis failed (non-critical): {e}")
            emotional_tone = "Neutral"

        # ── Commit Results ──────────────────────────────────────────────────────
        sentiment_confidence = 0.0
        try:
            if tone_out:
                sentiment_confidence = float(tone_out[0]["score"])
        except (KeyError, IndexError, TypeError):
            pass

        result.bias_profile = BiasProfile(
            bias_category=political_bias,
            bias_analysis_confidence=confidence,
            sentiment_category=emotional_tone,
            sentiment_analysis_confidence=sentiment_confidence,
        )
        message.set_nlp_result(result)
        logger.info(
            f"BiasDetector: Result — {political_bias} (conf={confidence:.2f}), "
            f"tone={emotional_tone}."
        )
