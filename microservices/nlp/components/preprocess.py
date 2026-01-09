import re
import logging
from typing import List

# Local imports
from models.base import NLPComponent
from schemas import ArticleInput, AnalysisResult, AnalysisOptions, SentenceScore

logger = logging.getLogger(__name__)

class Preprocessor(NLPComponent):
    """
    Handles text cleaning and sentence splitting.
    """
    def __init__(self):
        """
        Initializes the preprocessor.
        """
        pass

    def run(self, article: ArticleInput, result: AnalysisResult, options: AnalysisOptions) -> None:
        """
        Cleans the input text, splits it into sentences, and populates result.sentences.
        
        Args:
            article: The article input containing text.
            result: The analysis result to update (sentences).
            options: Configuration options.
        """
        # 1. Access the text (Handling potential field naming differences)
        # We try 'text' first, then 'content', default to empty string
        raw_text = getattr(article, 'text', getattr(article, 'content', ""))
        
        if not raw_text:
            logger.warning("Preprocessor received empty text.")
            result.sentences = []
            return

        # 2. Clean Text
        # Replace multiple newlines/tabs with a single space and trim
        cleaned_text = re.sub(r'\s+', ' ', raw_text).strip()
        
        # 3. Split Sentences
        # Split on punctuation (.!?) followed by space to keep punctuation attached
        # Logic: Look for . ! or ? -> check if followed by space -> split
        sentences_list = re.split(r'(?<=[.!?])\s+', cleaned_text)
        
        # 4. Populate AnalysisResult
        sentence_objects = []
        for idx, sent_text in enumerate(sentences_list):
            if not sent_text.strip():
                continue
            
            # Create the SentenceScore object defined in schemas.py
            # We initialize it with the text and index; scores/embeddings come later
            s_obj = SentenceScore(
                index=idx,
                text=sent_text.strip(),
                score=0.0,       # Default initialization
                embedding=None   # Will be filled by a later component
            )
            sentence_objects.append(s_obj)

        # Update the shared result object
        result.sentences = sentence_objects
        logger.info(f"Preprocessor: Split article into {len(sentence_objects)} sentences.")