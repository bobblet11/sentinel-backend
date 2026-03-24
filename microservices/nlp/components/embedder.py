import logging
from typing import Any, List

# Local imports
from microservices.nlp.models.base import NLPComponent
from common.models.api.redis_models import Article, NLPOptions, NLPResult
from microservices.nlp.config import EMBEDDING_MODEL

logger = logging.getLogger(__name__)

class Embedder(NLPComponent):
    """
    Generates vector embeddings for sentences using 'sentence-transformers/all-mpnet-base-v2'.
    These vectors (768-dim) are used for:
    1. Deduplication (finding similar sentences)
    2. Centrality (finding important sentences)
    3. Database Search (pgvector)
    """
    def __init__(self, model: Any = None):
        """
        Args:
            model: Loaded SentenceTransformer model.
        """
        self.model_name = EMBEDDING_MODEL
        
        if model:
            self.model = model
        else:
            from microservices.nlp.config import model_manager

            self.model = model_manager.get("EMBEDDING")

    def run(self, article: Article, result: NLPResult, options: NLPOptions) -> None:
        """
        Generates embeddings for all sentences in result.sentences.
        Updates result.sentences[i].embedding.
        """
        if not result.sentences:
            return

        # We encode the 'text' field (which might be decontextualized by now)
        texts = [s.text for s in result.sentences]
        
        try:
            # Batch Encode
            # show_progress_bar=False to keep logs clean in production
            embeddings = self.model.encode(texts, batch_size=32, show_progress_bar=False, convert_to_numpy=True)
            
            # Update Schema
            for i, sent in enumerate(result.sentences):
                # Convert numpy float32 array to standard list of floats for JSON/Pydantic serialization
                sent.embedding = embeddings[i].tolist()
                
            # Optional: Calculate Document Embedding (Average of sentence embeddings)
            # This is useful for "Article-level" similarity search
            if len(embeddings) > 0:
                doc_embedding = embeddings.mean(axis=0)
                result.doc_embedding = doc_embedding.tolist()
                
            logger.info(f"Embedder: Vectorized {len(texts)} sentences.")

        except Exception as e:
            logger.error(f"Embedder failed: {e}")
            raise
