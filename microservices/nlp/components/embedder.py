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
    """Sentence Embedding Layer.

    Generates dense vector embeddings for sentences using the
    'all-MiniLM-L6-v2' model (384-dimensional). Designed for efficient
    semantic similarity search and document retrieval.

    Model Details:
        - Architecture: all-MiniLM-L6-v2 (384-dim MiniLM variant)
        - Training: Trained on 215M sentence pairs for semantic similarity
        - Performance: Fast, efficient, suitable for pgvector storage
        - FP16 Support: Weights cast to float16 on CUDA for memory efficiency

    Processing Strategy:
        1. Batch inference via HuggingFace SentenceTransformer
        2. Texts wrapped in datasets.Dataset for zero-copy Arrow batching
        3. Batch size 32 (stable on GPU and CPU)
        4. Un-normalized embeddings (L2 magnitude preserved for downstream consumers)
        5. Document-level mean embedding computed for article-level similarity

    Contract:
        Input:  List[SentenceScore] with text populated
        Output: Same list with embedding field populated (in-place);
                does NOT modify article or message payload
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
        """Generate dense embeddings for all sentences.

        Encodes each sentence's text into a 384-dimensional vector using
        all-MiniLM-L6-v2 model. Updates SentenceScore.embedding in-place
        for each sentence with un-normalized vectors suitable for pgvector
        storage and semantic similarity search.

        Args:
            article: Article object (used for logging context)
            message: StreamMessage (used for logging context)
            options: NLPOptions (used for logging context)
            sentences: List[SentenceScore] to embed; text field required

        Returns:
            Same sentence list with embedding fields populated (384-dim lists)

        Raises:
            Exception: Encoding failure (model inference error, OOM, etc.)
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
