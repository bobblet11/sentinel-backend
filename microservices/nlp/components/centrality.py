import logging
import numpy as np
from typing import List

# Local imports
from microservices.nlp.models.base import NLPComponent
from common.models.api.redis_models import Article, NLPOptions, NLPResult

logger = logging.getLogger(__name__)

class CentralityScorer(NLPComponent):
    """
    Calculates importance scores for sentences using Eigenvector Centrality (LexRank).
    Identifies "hub" sentences that represent the main theme of the document.
    """
    def __init__(self):
        # No specific model needed here; it operates on existing embeddings.
        pass

    def run(self, article: Article, result: NLPResult, options: NLPOptions) -> None:
        """
        Assigns a centrality score (0.0 - 1.0) to each sentence based on its 
        similarity to all other sentences in the document.
        """
        if not options.enable_centrality:
            return

        sentences = result.sentences
        
        # Validation
        if not sentences:
            return
            
        # If only 1 sentence, it is 100% central
        if len(sentences) == 1:
            sentences[0].score = 1.0
            return

        # Check if embeddings exist
        if sentences[0].embedding is None:
            logger.warning("CentralityScorer: No embeddings found. Skipping.")
            return

        try:
            # 1. Prepare Matrix
            # Convert list of lists -> Numpy Array
            embeddings = np.array([s.embedding for s in sentences])
            
            # 2. Compute Cosine Similarity Matrix
            # (n, 768) @ (768, n) -> (n, n)
            # Clip negative scores to 0 (we only care about positive affinity)
            sim_matrix = np.maximum(np.dot(embeddings, embeddings.T), 0.0)

            # 3. Calculate Centrality
            try:
                # Method A: Eigenvector Centrality (LexRank)
                # Compute eigenvalues and right eigenvectors
                eigenvalues, eigenvectors = np.linalg.eig(sim_matrix)
                
                # The principal eigenvector corresponds to the largest eigenvalue
                # We take the real part (np.linalg.eig returns complex numbers sometimes)
                centrality_scores = np.abs(eigenvectors[:, 0])
                
            except np.linalg.LinAlgError:
                logger.warning("Centrality: Eigenvector calculation failed (singular matrix). Falling back to Degree Centrality.")
                # Method B: Degree Centrality (Fallback)
                # Simply sum the similarities (rows)
                centrality_scores = np.sum(sim_matrix, axis=1)

            # 4. Normalization (Min-Max Scaling)
            # We want scores between 0.0 and 1.0
            min_s = np.min(centrality_scores)
            max_s = np.max(centrality_scores)
            
            if max_s - min_s == 0:
                # If all scores are identical, give everyone 1.0
                norm_scores = np.ones(len(sentences))
            else:
                norm_scores = (centrality_scores - min_s) / (max_s - min_s)

            # 5. Update Results
            for i, score in enumerate(norm_scores):
                sentences[i].score = float(score)
                
            # Log the top sentence (Summary Candidate)
            top_idx = np.argmax(norm_scores)
            logger.info(f"Centrality: Top sentence: '{sentences[top_idx].text[:50]}...'")

        except Exception as e:
            logger.error(f"Centrality calculation failed: {e}")
            # Don't crash pipeline; just leave scores as default 0.0
