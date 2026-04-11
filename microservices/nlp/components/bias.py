import logging
import torch
from typing import Any, Dict, Optional
from transformers import pipeline

# Local imports
from microservices.nlp.models.base import ArticleProcessor
from microservices.nlp.components.device import DeviceConfig
from common.models.api.redis_models import Article, BiasProfile, Message, NLPOptions, NLPResult, StreamMessage
from microservices.nlp.config import (
    BIAS_POLITICAL_MODEL, BIAS_SENTIMENT_MODEL,
    BIAS_MAX_CHARS, BIAS_SENTIMENT_MAX_LEN,
)

logger = logging.getLogger(__name__)


class BiasDetector(ArticleProcessor):
    """
    MODULAR BIAS DETECTION LAYER

    Performs article-level political bias classification and emotional tone
    analysis using two lightweight NLI/sentiment transformer pipelines.

    Strategies Applied:
    1.  Political Bias via Zero-Shot NLI (typeform/distilbert-base-uncased-mnli):
        The article text (truncated to POLITICAL_MAX_CHARS characters) is classified
        against three mutually exclusive hypothesis labels:
        ["left-leaning", "centrist", "right-leaning"].
        The model operates via soft-NLI entailment — no political fine-tuning is
        required, making it robust to domain shift across news publishers.
        Scores are normalised across labels using the model's own softmax
        (hypothesis_template='This text has a {} political perspective.').
    2.  Emotional Tone via Sentiment Analysis (cardiffnlp/twitter-roberta-base-sentiment-latest):
        The same truncated text is scored for emotional polarity.
        The top label from {negative, neutral, positive} is mapped to
        a human-readable tone string ("Negative", "Neutral", "Positive") and
        stored in BiasProfile.emotional_tone.
    3.  Text Truncation: Analysis is bounded to the first POLITICAL_MAX_CHARS
        (default 2000) characters of the article body. This keeps inference
        fast (< 1 s on CPU for most articles) while capturing the lede and early
        paragraphs that typically set the article's framing.
    4.  FP16: Both pipelines use float16 on CUDA to reduce memory usage.
    5.  Graceful Degradation: On any inference failure, a neutral / zero-confidence
        BiasProfile is stored and the error is logged — the pipeline is never blocked.

    Writes to result.bias_profile only; does NOT modify sentences.
    """

    POLITICAL_LABELS = ["left-leaning", "centrist", "right-leaning"]
    # Map classifier output labels to the canonical BiasProfile string format
    _LABEL_MAP = {
        "left-leaning":  "Left",
        "centrist":      "Center",
        "right-leaning": "Right",
    }
    _TONE_MAP = {
        "negative": "Negative",
        "neutral":  "Neutral",
        "positive": "Positive",
    }

    def __init__(self, device_config: DeviceConfig, model_manager: Optional[Any] = None):
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

            self.political_classifier = pipeline(
                "zero-shot-classification",
                model=BIAS_POLITICAL_MODEL,
                device=device_config.device_id,
                dtype=device_config.dtype,
            )
            self.sentiment_analyzer = pipeline(
                "sentiment-analysis",
                model=BIAS_SENTIMENT_MODEL,
                device=device_config.device_id,
                dtype=device_config.dtype,
                truncation=True,
                max_length=BIAS_SENTIMENT_MAX_LEN,
            )
            logger.info("BiasDetector: Models loaded successfully.")
        except Exception as e:
            logger.error(f"BiasDetector: Failed to load models: {e}")
            raise

    def _neutral_profile(self) -> BiasProfile:
        """Returns a zero-confidence neutral bias profile for graceful degradation."""
        return BiasProfile(
            bias_category="Center",
            bias_score=0.0,
            bias_analysis_confidence=0.0,
            sentiment_category="Neutral",
            sentiment_analysis_confidence=0.0,
        )

    def run(self, article: Article, message: StreamMessage, options: NLPOptions) -> None:
        """
        Classifies the article's political lean and emotional tone.
        Writes the result to result.bias_profile.
        Does NOT return a value.
        """
        text = (article.text or article.summary or "").strip()
        if not text:
            logger.warning("BiasDetector: No text available — using neutral profile.")
            result = message.create_nlp_result()
            result.bias_profile = self._neutral_profile()
            message.set_nlp_result(result)
            return

        analysis_text = text[:BIAS_MAX_CHARS]

        # ── Political Bias ──────────────────────────────────────────────────────
        try:
            bias_out = self.political_classifier(
                analysis_text,
                self.POLITICAL_LABELS,  # class-level label list; unchanged
                multi_label=False,
                hypothesis_template="This text has a {} political perspective.",
            )
            raw_label  = bias_out["labels"][0]          # e.g. "left-leaning"
            confidence = float(bias_out["scores"][0])

            # Build canonical scores dict using BiasProfile keys
            scores: Dict[str, float] = {
                self._LABEL_MAP[lbl]: float(sc)
                for lbl, sc in zip(bias_out["labels"], bias_out["scores"])
            }
            political_bias = self._LABEL_MAP.get(raw_label, "Center")

        except Exception as e:
            logger.error(f"BiasDetector: Political bias classification failed: {e}")
            result.bias_profile = self._neutral_profile()
            return

        # ── Emotional Tone ──────────────────────────────────────────────────────
        emotional_tone: Optional[str] = None
        tone_out = None
        try:
            tone_out   = self.sentiment_analyzer(analysis_text[:512])
            raw_tone   = tone_out[0]["label"].lower() if tone_out else "neutral"
            emotional_tone = self._TONE_MAP.get(raw_tone, raw_tone.capitalize())
        except Exception as e:
            logger.warning(f"BiasDetector: Tone analysis failed (non-critical): {e}")
            emotional_tone = "Neutral"

        # ── Commit Results ──────────────────────────────────────────────────────
        # Pick the top score from the political bias scores dict as bias_score
        bias_score = max(scores.values()) if scores else 0.0
        sentiment_confidence = 0.0
        try:
            if tone_out:
                sentiment_confidence = float(tone_out[0]["score"])
        except (KeyError, IndexError, TypeError):
            pass
        
        result = message.create_nlp_result()
        result.bias_profile = BiasProfile(
            bias_category=political_bias,
            bias_score=bias_score,
            bias_analysis_confidence=confidence,
            sentiment_category=emotional_tone,
            sentiment_analysis_confidence=sentiment_confidence,
        )
        message.set_nlp_result(result)
        logger.info(
            f"BiasDetector: Result — {political_bias} (conf={confidence:.2f}), "
            f"tone={emotional_tone}."
        )
