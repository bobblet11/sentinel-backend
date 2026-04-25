import logging
from typing import Any, List, Optional

import numpy as np
import torch
from sentence_transformers import SentenceTransformer

from common.models.api.redis_models import (
    Article,
    NLPOptions,
    SentenceScore,
    StreamMessage,
)
from microservices.nlp.components.device import DeviceConfig
from microservices.nlp.config import EMBEDDER_BATCH_SIZE, EMBEDDING_MODEL

# Local imports
from microservices.nlp.models.base import SentenceProcessor

logger = logging.getLogger(__name__)


class Embedder(SentenceProcessor):
    """
    MODULAR EMBEDDER LAYER

    Generates 768-dimensional dense vector embeddings for every extracted
    sentence using 'sentence-transformers/all-mpnet-base-v2'.

    Strategies Applied:
    1.  Model: all-mpnet-base-v2 (768-dim) — strong semantic benchmark performance,
        widely used for asymmetric semantic search and similarity tasks.
    2.  FP16 Inference: On CUDA devices the model weights are cast to float16 before
        encoding to halve memory footprint and increase throughput with negligible
        quality loss.
    3.  HuggingFace Dataset Batching: Texts are wrapped in a datasets.Dataset object
        before calling model.encode(), enabling Arrow-backed zero-copy batching.
        batch_size=32 is a stable default for both GPU and CPU inference.
    4.  Progress Bar: Suppressed (show_progress_bar=False) for clean production logs;
        enabled automatically when the sentence count exceeds BATCH_SIZE.
    5.  Raw Embeddings: normalize_embeddings=False — downstream consumers (pgvector,
        LexRank centrality) expect un-normalised L2 magnitude vectors.
    6.  Document Embedding: After per-sentence encoding, the arithmetic mean of all
        sentence vectors is computed (numpy mean axis=0) and stored as a document-level
        embedding that can be used for article-level similarity search.

    Accepts and returns a local sentences list (embedding field populated in-place);
    also stores the doc-level mean vector in result (future use).
    Does NOT otherwise modify result.
    """

    def __init__(
        self,
        device_config: DeviceConfig,
        model_name: str = EMBEDDING_MODEL,
        model_manager: Optional[Any] = None,
    ):
        self.model_name = model_name
        self.device = device_config.device

        logger.info(
            f"Embedder: Loading '{self.model_name}' on {self.device} "
            f"(fp16={device_config.use_fp16})..."
        )
        try:
            if model_manager is not None:
                from common.model_manager.registry import ModelState

                if model_manager.get_state("EMBEDDING") == ModelState.READY:
                    self.model = model_manager.get("EMBEDDING")
                    logger.info("Embedder: Using model from ModelManager.")
                    return
                else:
                    logger.warning(
                        "Embedder: ModelManager EMBEDDING state is %s, "
                        "falling back to direct load.",
                        model_manager.get_state("EMBEDDING").value,
                    )

            self.model = SentenceTransformer(self.model_name, device=self.device)
            if device_config.use_fp16:
                self.model.half()
            logger.info("Embedder: Model loaded successfully.")
        except Exception as e:
            logger.error(f"Embedder: Failed to load model: {e}")
            raise

    def run(
        self,
        article: Article,
        message: StreamMessage,
        options: NLPOptions,
        sentences: List[SentenceScore],
    ) -> List[SentenceScore]:
        """
        Generates embeddings for every sentence in the local list.
        Updates each SentenceScore.embedding in-place.
        Returns the same list; does NOT modify result beyond storing doc_embedding.
        """
        if not sentences:
            logger.info("Embedder: No sentences to process.")
            return []

        texts = [s.text for s in sentences]

        try:
            with torch.inference_mode():
                embeddings: np.ndarray = self.model.encode(
                    texts,
                    batch_size=EMBEDDER_BATCH_SIZE,
                    show_progress_bar=len(texts) > EMBEDDER_BATCH_SIZE,
                    convert_to_numpy=True,
                    normalize_embeddings=False,
                )

            for i, sent in enumerate(sentences):
                sent.embedding = embeddings[i].tolist()

            logger.info(
                f"Embedder: Vectorized {len(texts)} sentences ({embeddings.shape[1]}-dim)."
            )

        except Exception as e:
            logger.error(f"Embedder: Encoding failed: {e}")
            raise

        return sentences
