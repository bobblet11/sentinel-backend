import logging
import torch
import re
import numpy as np
from typing import List, Set, Tuple

# Local imports
from microservices.nlp.models.base import NLPComponent
from common.models.api.redis_models import Article, NLPOptions, NLPResult

logger = logging.getLogger(__name__)

class Deduplicator(NLPComponent):
    """
    Hybrid Deduplicator:
    1. Uses Vector Semantic Clustering (Fast) to find candidates.
    2. Applies Lexical Heuristics (Negation/Numbers) to prevent dangerous merges.
    """
    def __init__(self, threshold: float = 0.85):
        """
        Args:
            threshold (float): Similarity score (0.0 to 1.0) for clustering.
        """
        self.threshold = threshold
        # Negation terms to watch out for
        self.negations = {"not", "no", "never", "n't", "neither", "nor", "none"}

    def _is_lexically_safe(self, s1: str, s2: str) -> Tuple[bool, str]:
        """
        Returns True if it is 'safe' to merge these two sentences.
        Checks for:
        1. Negation mismatches (The deal is signed vs The deal is NOT signed)
        2. Numerical mismatches (3% vs 30%)
        """
        text1 = s1.lower()
        text2 = s2.lower()
        
        # A. Negation Check
        # We split by whitespace to avoid matching 'not' inside 'nothing' or 'notion' imperfectly
        tokens1 = set(re.findall(r"\b[\w']+\b", text1))
        tokens2 = set(re.findall(r"\b[\w']+\b", text2))

        s1_has_neg = not tokens1.isdisjoint(self.negations)
        s2_has_neg = not tokens2.isdisjoint(self.negations)
        
        if s1_has_neg != s2_has_neg:
            return False, "Negation Mismatch"
            
        # B. Numbers Check
        # Extract numbers (integers and floats)
        nums1 = set(re.findall(r'\d+\.?\d*', text1))
        nums2 = set(re.findall(r'\d+\.?\d*', text2))
        
        # If both have numbers, they must match perfectly
        if nums1 and nums2 and nums1 != nums2:
            return False, f"Number Mismatch ({nums1} vs {nums2})"
        
        return True, "Safe"

    def run(self, article: Article, result: NLPResult, options: NLPOptions) -> None:
        """
        Filters result.sentences in-place using Hybrid Deduplication.
        """
        sentences = result.sentences
        
        # 1. Validation
        if not sentences or len(sentences) < 2:
            return
            
        if sentences[0].embedding is None:
            logger.warning("Deduplicator: No embeddings found. Skipping.")
            return

        try:
            # 2. Prepare Embeddings Tensor
            embeddings_list = [s.embedding for s in sentences]
            
            # Detect device dynamically (cpu is safer for small batches if not already on gpu)
            # But community_detection often runs faster on CPU for small N
            device = "cpu" 
            
            # Convert to tensor
            embeddings_tensor = torch.tensor(embeddings_list).to(device)

            # 3. Semantic Clustering (The Heavy Lifting)
            # community_detection is optimized for finding groups in large lists
            from sentence_transformers import util
            
            # Returns list of clusters, e.g., [[0, 3], [1], [2, 5]]
            # The first element in each sublist is the "centroid" or "keeper"
            clusters = util.community_detection(
                embeddings_tensor, 
                min_community_size=1, 
                threshold=self.threshold
            )

            # 4. Hybrid Filtering
            indices_to_remove = set()
            
            for cluster in clusters:
                # cluster[0] is the "Anchor" (The one we intend to keep)
                anchor_idx = cluster[0]
                anchor_text = sentences[anchor_idx].text
                
                # Check the rest of the cluster against the anchor
                if len(cluster) > 1:
                    for duplicate_idx in cluster[1:]:
                        duplicate_text = sentences[duplicate_idx].text
                        
                        # Apply Safety Valve
                        safe, reason = self._is_lexically_safe(anchor_text, duplicate_text)
                        
                        if safe:
                            indices_to_remove.add(duplicate_idx)
                            # logger.debug(f"Merged: '{duplicate_text}' -> '{anchor_text}'")
                        else:
                            # If unsafe, we DO NOT remove it. It effectively becomes its own singleton.
                            # logger.info(f"Saved from Merge: '{duplicate_text}' (Reason: {reason})")
                            pass

            # 5. Rebuild Result
            if indices_to_remove:
                original_count = len(sentences)
                
                # Filter the list
                result.sentences = [
                    s for idx, s in enumerate(sentences) 
                    if idx not in indices_to_remove
                ]
                
                logger.info(f"Deduplicator: Removed {len(indices_to_remove)} duplicates. {original_count} -> {len(result.sentences)} sentences.")
                            
        except Exception as e:
            logger.error(f"Deduplication failed: {e}")
            # On error, do nothing (safe fallback)
