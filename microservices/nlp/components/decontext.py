from typing import List, Tuple
from microservices.nlp.models.base import Seq2SeqRewriter
from microservices.nlp.types import Claim

class Decontextualizer:
    """
    Rewrites claims to be self-contained by resolving coreferences and adding context.
    """
    def __init__(self, rewriter: Seq2SeqRewriter):
        """
        Initializes the decontextualizer with a rewriter model.
        """
        pass

    def run(self, claims: List[Claim], full_text: str) -> List[Claim]:
        """
        Processes claims to make them standalone.
        
        Args:
            claims: List of claims to decontextualize.
            full_text: The original context text.
            
        Returns:
            List of modified claims with resolved context.
        """
        pass
