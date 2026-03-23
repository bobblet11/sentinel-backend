import logging
from typing import Any, Dict, List

from microservices.nlp.models.base import NLPComponent
from common.models.api.redis_models import Article, BiasProfile, NLPOptions, NLPResult
from microservices.nlp.config import BIAS_MODEL

logger = logging.getLogger(__name__)

class BiasDetector(NLPComponent):
    """
    Detects political bias and sentiment using zero-shot classification.

    Outputs:
    - result.bias_profile (article-level summary)
    - sentence.metadata["bias"] (sentence-level category/confidence)

    Note: We never overwrite sentence.score because that field is used by
    centrality ranking and downstream claim selection.
    """
    POLITICAL_LABELS: List[str] = ["left", "center", "right"]
    SENTIMENT_LABELS: List[str] = ["positive", "neutral", "negative"]
    MAX_ARTICLE_TEXT_CHARS: int = 6000
    MAX_SENTENCES_TO_CLASSIFY: int = 30
    TEXT_CLASSIFICATION_MAX_CHARS: int = 2000

    def __init__(self, model: Any = None):
        """
        Args:
            model: Optional injected zero-shot classification pipeline.
        """
        self.model = model
        self.model_mode = "unknown"

        if self.model is None:
            logger.info("BiasDetector: Loading model '%s'...", BIAS_MODEL)
            try:
                torch_module = __import__("torch")
                transformers_module = __import__("transformers", fromlist=["pipeline"])
                hf_pipeline = getattr(transformers_module, "pipeline")

                device = 0 if torch_module.cuda.is_available() else -1
                model_name = str(BIAS_MODEL).lower()

                # For non-MNLI models (e.g. toxic-bert), use text-classification.
                if "mnli" in model_name:
                    self.model = hf_pipeline(
                        "zero-shot-classification",
                        model=BIAS_MODEL,
                        device=device,
                    )
                    self.model_mode = "zero-shot"
                else:
                    self.model = hf_pipeline(
                        "text-classification",
                        model=BIAS_MODEL,
                        device=device,
                        return_all_scores=True,
                    )
                    self.model_mode = "text-classification"

                logger.info("BiasDetector: Loaded on %s.", "GPU" if device == 0 else "CPU")
            except Exception as exc:
                logger.error("BiasDetector: Failed to load model: %s", exc)
                self.model = None
                self.model_mode = "unknown"
        else:
            # Default assumption for injected models in current pipeline/tests.
            self.model_mode = "zero-shot"

    def _neutral_profile(self) -> BiasProfile:
        return BiasProfile(
            bias_category="center",
            bias_score=0.0,
            bias_analysis_confidence=0.0,
            sentiment_category="neutral",
            sentiment_analysis_confidence=0.0,
        )

    def _classify(self, text: str, labels: List[str], hypothesis_template: str) -> Dict[str, float]:
        if not self.model or self.model_mode != "zero-shot":
            return {}

        pred = self.model(
            text,
            labels,
            multi_label=False,
            hypothesis_template=hypothesis_template,
        )

        # Normalize output into a label->score mapping.
        return {
            str(label).lower(): float(score)
            for label, score in zip(pred.get("labels", []), pred.get("scores", []))
        }

    def _classify_toxicity(self, text: str) -> Dict[str, float]:
        if not self.model or self.model_mode != "text-classification":
            return {}

        safe_text = text[: self.TEXT_CLASSIFICATION_MAX_CHARS]
        raw = self.model(safe_text)

        # text-classification with return_all_scores=True returns [[{label,score}, ...]].
        rows = raw[0] if raw and isinstance(raw[0], list) else raw
        if not rows:
            return {}

        scores: Dict[str, float] = {}
        for row in rows:
            label = str(row.get("label", "")).strip().lower()
            score = float(row.get("score", 0.0))
            if not label:
                continue
            scores[label] = score

        return scores

    def _resolve_toxic_score(self, scores: Dict[str, float]) -> float:
        if not scores:
            return 0.0

        for label, value in scores.items():
            if "toxic" in label and "non" not in label:
                return float(value)

        # Common binary classifier fallback: LABEL_1 is typically positive class.
        if "label_1" in scores:
            return float(scores["label_1"])

        top_label = max(scores, key=lambda name: scores[name])
        return float(scores[top_label])

    def _article_text(self, article: Article, result: NLPResult) -> str:
        text = (article.text or "").strip()
        if text:
            return text[: self.MAX_ARTICLE_TEXT_CHARS]

        if result.sentences:
            joined = " ".join(s.text for s in result.sentences if s.text)
            return joined[: self.MAX_ARTICLE_TEXT_CHARS]

        return ""

    def _annotate_sentences(self, sentences) -> None:
        if not sentences or not self.model:
            return

        ranked = sorted(
            sentences,
            key=lambda s: s.score if s.score is not None else 0.0,
            reverse=True,
        )
        selected = ranked[: self.MAX_SENTENCES_TO_CLASSIFY]

        for sentence in selected:
            text = (sentence.text or "").strip()
            if not text:
                continue

            try:
                if self.model_mode == "zero-shot":
                    bias_scores = self._classify(
                        text,
                        self.POLITICAL_LABELS,
                        "The political perspective of this sentence is {}.",
                    )

                    if not bias_scores:
                        continue

                    category = max(bias_scores, key=lambda label: bias_scores[label])
                    sentence.metadata["bias"] = {
                        "category": category,
                        "confidence": float(bias_scores[category]),
                        "scores": bias_scores,
                    }
                elif self.model_mode == "text-classification":
                    scores = self._classify_toxicity(text)
                    if not scores:
                        continue

                    toxic_score = self._resolve_toxic_score(scores)
                    category = "biased" if toxic_score >= 0.5 else "center"
                    sentence.metadata["bias"] = {
                        "category": category,
                        "confidence": float(toxic_score),
                        "scores": scores,
                    }
            except Exception as exc:
                logger.debug("BiasDetector: Sentence annotation failed: %s", exc)

    def run(self, article: Article, result: NLPResult, options: NLPOptions) -> None:
        """
        Populates result.bias_profile with article-level political bias + sentiment.
        """
        if not options.enable_bias_detection:
            return

        text = self._article_text(article, result)
        if not text:
            logger.warning("BiasDetector: No text available for bias analysis.")
            result.bias_profile = self._neutral_profile()
            return

        if not self.model:
            logger.warning("BiasDetector: Model unavailable; using neutral fallback.")
            result.bias_profile = self._neutral_profile()
            return

        try:
            if self.model_mode == "zero-shot":
                political_scores = self._classify(
                    text,
                    self.POLITICAL_LABELS,
                    "The political leaning of this text is {}.",
                )
                sentiment_scores = self._classify(
                    text,
                    self.SENTIMENT_LABELS,
                    "The sentiment of this text is {}.",
                )

                if not political_scores or not sentiment_scores:
                    result.bias_profile = self._neutral_profile()
                    return

                bias_category = max(political_scores, key=lambda label: political_scores[label])
                sentiment_category = max(sentiment_scores, key=lambda label: sentiment_scores[label])

                # Bias strength, independent of left/right direction.
                bias_strength = 1.0 - political_scores.get("center", 0.0)

                result.bias_profile = BiasProfile(
                    bias_category=bias_category,
                    bias_score=float(max(0.0, min(1.0, bias_strength))),
                    bias_analysis_confidence=float(political_scores[bias_category]),
                    sentiment_category=sentiment_category,
                    sentiment_analysis_confidence=float(sentiment_scores[sentiment_category]),
                )
            elif self.model_mode == "text-classification":
                toxicity_scores = self._classify_toxicity(text)
                if not toxicity_scores:
                    result.bias_profile = self._neutral_profile()
                    return

                toxic_score = float(max(0.0, min(1.0, self._resolve_toxic_score(toxicity_scores))))
                sentiment_category = "negative" if toxic_score >= 0.6 else "neutral"

                # Toxicity models do not provide left/center/right direction.
                result.bias_profile = BiasProfile(
                    bias_category="center",
                    bias_score=toxic_score,
                    bias_analysis_confidence=toxic_score,
                    sentiment_category=sentiment_category,
                    sentiment_analysis_confidence=toxic_score,
                )
            else:
                result.bias_profile = self._neutral_profile()
                return

            self._annotate_sentences(result.sentences)

            logger.info(
                "BiasDetector: bias=%s (conf=%.3f) sentiment=%s (conf=%.3f)",
                result.bias_profile.bias_category,
                result.bias_profile.bias_analysis_confidence,
                result.bias_profile.sentiment_category,
                result.bias_profile.sentiment_analysis_confidence,
            )

        except Exception as exc:
            logger.error("BiasDetector failed: %s", exc)
            result.bias_profile = self._neutral_profile()
