import logging
import torch
import numpy as np
import torch.nn.functional as F
from typing import List
from transformers import AutoTokenizer, AutoModel, AutoModelForSequenceClassification
from torch.amp import autocast

# Local imports
from microservices.nlp.models.base import NLPComponent
from common.models.api.redis_models import Article, NLPOptions, NLPResult, SentenceScore
from microservices.nlp.config import (
    BERT_SCORING_MODEL, NLI_MODEL,
    SENTENCE_SCORING_BATCH, NLI_MAX_PAIRS,
    NLI_ENTAILMENT_THRESHOLD, BERT_MAX_LENGTH,
    SENTENCE_EXTRACT_TOP_K,
)

logger = logging.getLogger(__name__)

class SentenceExtraction(NLPComponent):
    """
    MODULAR SENTENCE EXTRACTION LAYER
    Combines extractive importance (BertSum-style CLS scoring) with
    logical deduplication (NLI cross-encoder).

    Accepts and returns a local sentences list; does NOT touch result.
    """
    def __init__(self, use_fp16: bool = True):
        self.use_fp16 = use_fp16 and torch.cuda.is_available()
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

        logger.info(f"SentenceExtraction: Initializing models on {self.device} "
                    f"(fp16={self.use_fp16})...")

        try:
            self.tokenizer = AutoTokenizer.from_pretrained(BERT_SCORING_MODEL)
            self.scoring_model = AutoModel.from_pretrained(BERT_SCORING_MODEL).to(self.device)

            self.nli_tokenizer = AutoTokenizer.from_pretrained(NLI_MODEL)
            self.nli_model = (
                AutoModelForSequenceClassification
                .from_pretrained(NLI_MODEL)
                .to(self.device)
            )

            if self.use_fp16:
                self.scoring_model = self.scoring_model.half()
                self.nli_model = self.nli_model.half()
        except Exception as e:
            logger.error(f"SentenceExtraction: Failed to load models: {e}")
            raise

    def _get_salience_scores(self, sentences: List[str]) -> np.ndarray:
        scores = []
        with torch.no_grad():
            # Use autocast for mixed precision if enabled
            with autocast(device_type=("cuda" if "cuda" in self.device else "cpu"), enabled=self.use_fp16):
                for start in range(0, len(sentences), SENTENCE_SCORING_BATCH):
                    batch_texts = sentences[start : start + SENTENCE_SCORING_BATCH]
                    inputs = self.tokenizer(
                        batch_texts,
                        return_tensors="pt",
                        padding=True,
                        truncation=True,
                        max_length=BERT_MAX_LENGTH,
                    ).to(self.device)
                    
                    outputs = self.scoring_model(**inputs)
                    # Use CLS token vector (index 0) for sentence representation
                    cls_vecs = outputs.last_hidden_state[:, 0, :]
                    # Mean of absolute values as a proxy for "information density"
                    batch_scores = torch.mean(torch.abs(cls_vecs), dim=-1)
                    scores.extend(batch_scores.cpu().float().tolist())

        scores = np.array(scores)
        # Min-Max Normalization
        return (
            (scores - scores.min()) / (scores.max() - scores.min() + 1e-10)
            if len(scores) > 1
            else scores
        )

    def _is_redundant(self, candidate: str, already_selected: List[str]) -> bool:
        if not already_selected:
            return False

        # Prepare pairs for the Cross-Encoder
        pairs = [[prev, candidate] for prev in already_selected]
        # Limit the number of NLI checks to avoid quadratic explosion
        pairs = pairs[-NLI_MAX_PAIRS:]

        with torch.no_grad():
            with autocast(device_type=("cuda" if "cuda" in self.device else "cpu"), enabled=self.use_fp16):
                inputs = self.nli_tokenizer(
                    pairs,
                    return_tensors="pt",
                    padding=True,
                    truncation=True,
                    max_length=BERT_MAX_LENGTH,
                ).to(self.device)

                outputs = self.nli_model(**inputs)
                # index 1 is usually 'entailment' in NLI models
                probs = F.softmax(outputs.logits.float(), dim=-1)
                return bool((probs[:, 1] > NLI_ENTAILMENT_THRESHOLD).any())

    def run(self, article: Article, result: NLPResult, options: NLPOptions,
            sentences: List[SentenceScore]) -> List[SentenceScore]:
        """
        Scores and deduplicates sentences.
        Returns a filtered local list of high-value sentences.
        """
        if not sentences:
            return []

        raw_texts = [s.text for s in sentences]
        scores = self._get_salience_scores(raw_texts)

        # Rank indices by score descending
        ranked_indices = np.argsort(scores)[::-1]
        selected_indices: List[int] = []
        selected_texts:   List[str] = []

        # Get limit from options or fall back to the configured default
        limit = getattr(options, "max_claims", SENTENCE_EXTRACT_TOP_K)

        for idx in ranked_indices:
            if len(selected_indices) >= limit:
                break
            
            candidate = raw_texts[idx]
            # Cross-Encoder check to ensure this sentence adds new information
            if not self._is_redundant(candidate, selected_texts):
                selected_indices.append(int(idx))
                selected_texts.append(candidate)
                # Assign the calculated salience score to the object
                sentences[idx].score = float(scores[idx])

        # Return the selected sentences sorted by their original order in the text
        extracted = [sentences[i] for i in sorted(selected_indices)]
        logger.info(f"SentenceExtraction: Extracted {len(extracted)} salient, unique sentences.")
        return extracted
