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
<<<<<<< HEAD
    1.  Political Bias via Zero-Shot NLI (typeform/distilbert-base-uncased-mnli):
        The article text (truncated to POLITICAL_MAX_CHARS characters) is classified
        against three mutually exclusive hypothesis labels:
        ["left-leaning", "centrist", "right-leaning"].
        The model operates via soft-NLI entailment — no political fine-tuning is
        required, making it robust to domain shift across news publishers.
        Scores are normalised across labels using the model's own softmax
        (hypothesis_template='This text has a {} political perspective.').
=======
    1.  Political Bias via Direct Classification (premsa/political-bias-prediction-allsides-BERT):
        The article text (truncated to BIAS_MAX_CHARS characters) is classified into
        one of three categories: Left, Center, or Right. The model is fine-tuned on
        AllSides-rated news articles (F1=0.904). Label mapping: LABEL_0=Left,
        LABEL_1=Center, LABEL_2=Right (AllSides dataset standard ordering).
>>>>>>> 029c55eb28ec7683a93e17d0ad574b6aff998cac
    2.  Emotional Tone via Sentiment Analysis (cardiffnlp/twitter-roberta-base-sentiment-latest):
        The same truncated text is scored for emotional polarity.
        The top label from {negative, neutral, positive} is mapped to
        a human-readable tone string ("Negative", "Neutral", "Positive") and
        stored in BiasProfile.emotional_tone.
<<<<<<< HEAD
    3.  Text Truncation: Analysis is bounded to the first POLITICAL_MAX_CHARS
=======
    3.  Text Truncation: Analysis is bounded to the first BIAS_MAX_CHARS
>>>>>>> 029c55eb28ec7683a93e17d0ad574b6aff998cac
        (default 2000) characters of the article body. This keeps inference
        fast (< 1 s on CPU for most articles) while capturing the lede and early
        paragraphs that typically set the article's framing.
    4.  FP16: Both pipelines use float16 on CUDA to reduce memory usage.
    5.  Graceful Degradation: On any inference failure, a neutral / zero-confidence
        BiasProfile is stored and the error is logged — the pipeline is never blocked.

    Writes to result.bias_profile only; does NOT modify sentences.
    """

<<<<<<< HEAD
    POLITICAL_LABELS = ["left-leaning", "centrist", "right-leaning"]
    # Map classifier output labels to the canonical BiasProfile string format
    _LABEL_MAP = {
        "left-leaning":  "Left",
        "centrist":      "Center",
        "right-leaning": "Right",
=======
    # premsa/political-bias-prediction-allsides-BERT label mapping
    # Dataset label order: 0=Left, 1=Center, 2=Right
    _LABEL_MAP = {
        "LABEL_0": "Left",
        "LABEL_1": "Center",
        "LABEL_2": "Right",
>>>>>>> 029c55eb28ec7683a93e17d0ad574b6aff998cac
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

<<<<<<< HEAD
            self.political_classifier = pipeline(
                "zero-shot-classification",
                model=BIAS_POLITICAL_MODEL,
                device=device_config.device_id,
                dtype=device_config.dtype,
=======
            _dtype_kwargs = {"dtype": device_config.dtype} if device_config.use_fp16 else {}
            self.political_classifier = pipeline(
                "text-classification",
                model=BIAS_POLITICAL_MODEL,
                device=device_config.device_id,
                top_k=None,
                truncation=True,
                max_length=512,
                **_dtype_kwargs,
>>>>>>> 029c55eb28ec7683a93e17d0ad574b6aff998cac
            )
            self.sentiment_analyzer = pipeline(
                "sentiment-analysis",
                model=BIAS_SENTIMENT_MODEL,
                device=device_config.device_id,
<<<<<<< HEAD
                dtype=device_config.dtype,
                truncation=True,
                max_length=BIAS_SENTIMENT_MAX_LEN,
=======
                truncation=True,
                max_length=BIAS_SENTIMENT_MAX_LEN,
                **_dtype_kwargs,
>>>>>>> 029c55eb28ec7683a93e17d0ad574b6aff998cac
            )
            logger.info("BiasDetector: Models loaded successfully.")
        except Exception as e:
            logger.error(f"BiasDetector: Failed to load models: {e}")
            raise

    def _neutral_profile(self) -> BiasProfile:
        """Returns a zero-confidence neutral bias profile for graceful degradation."""
        return BiasProfile(
            bias_category="Center",
<<<<<<< HEAD
            bias_score=0.0,
=======
>>>>>>> 029c55eb28ec7683a93e17d0ad574b6aff998cac
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

<<<<<<< HEAD
=======
        result = message.create_nlp_result()
>>>>>>> 029c55eb28ec7683a93e17d0ad574b6aff998cac
        analysis_text = text[:BIAS_MAX_CHARS]

        # ── Political Bias ──────────────────────────────────────────────────────
        try:
<<<<<<< HEAD
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
=======
            bias_out_raw = self.political_classifier(analysis_text)
            # top_k=None returns [[{label, score}, ...]] for a single string — unwrap batch dim
            bias_out: list = bias_out_raw[0] if bias_out_raw and isinstance(bias_out_raw[0], list) else bias_out_raw
            # Sort descending by score to get top prediction first
            bias_out = sorted(bias_out, key=lambda x: x["score"], reverse=True)
            raw_label  = bias_out[0]["label"]
            confidence = float(bias_out[0]["score"])
            scores: Dict[str, float] = {
                self._LABEL_MAP.get(item["label"], "Center"): float(item["score"])
                for item in bias_out
>>>>>>> 029c55eb28ec7683a93e17d0ad574b6aff998cac
            }
            political_bias = self._LABEL_MAP.get(raw_label, "Center")

        except Exception as e:
            logger.error(f"BiasDetector: Political bias classification failed: {e}")
            result.bias_profile = self._neutral_profile()
<<<<<<< HEAD
=======
            message.set_nlp_result(result)
>>>>>>> 029c55eb28ec7683a93e17d0ad574b6aff998cac
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
<<<<<<< HEAD
        # Pick the top score from the political bias scores dict as bias_score
        bias_score = max(scores.values()) if scores else 0.0
=======
>>>>>>> 029c55eb28ec7683a93e17d0ad574b6aff998cac
        sentiment_confidence = 0.0
        try:
            if tone_out:
                sentiment_confidence = float(tone_out[0]["score"])
        except (KeyError, IndexError, TypeError):
            pass
<<<<<<< HEAD
        
        result = message.create_nlp_result()
        result.bias_profile = BiasProfile(
            bias_category=political_bias,
            bias_score=bias_score,
=======

        result.bias_profile = BiasProfile(
            bias_category=political_bias,
>>>>>>> 029c55eb28ec7683a93e17d0ad574b6aff998cac
            bias_analysis_confidence=confidence,
            sentiment_category=emotional_tone,
            sentiment_analysis_confidence=sentiment_confidence,
        )
        message.set_nlp_result(result)
        logger.info(
            f"BiasDetector: Result — {political_bias} (conf={confidence:.2f}), "
            f"tone={emotional_tone}."
        )
