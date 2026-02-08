import logging
import spacy
from typing import List

# Local imports
from microservices.nlp.models.base import NLPComponent
from common.models.api.redis_models import Article, NLPOptions, NLPResult, SentenceScore

logger = logging.getLogger(__name__)

class Preprocessor(NLPComponent):
    """
    Handles text cleaning and sentence splitting using Spacy.
    """
    def __init__(self):
        """
        Initializes the preprocessor and loads the Spacy model.
        """
        logger.info("Preprocessor: Loading Spacy 'en_core_web_sm' model...")
        try:
            # Disable components we don't need for splitting (speed optimization)
            self.nlp = spacy.load("en_core_web_sm", disable=["ner", "tagger", "lemmatizer", "attribute_ruler"])
        except OSError:
            logger.error("Spacy model 'en_core_web_sm' not found. Run: python -m spacy download en_core_web_sm")
            raise


    def run(self, article: Article, result: NLPResult, options: NLPOptions) -> None:
        """
        Cleans the input text, splits it into sentences using Spacy, and populates result.sentences.
        """
        # 1. Access the text
        raw_text = getattr(article, 'text', getattr(article, 'content', ""))
        
        if not raw_text:
            logger.warning("Preprocessor: Received empty text.")
            result.sentences = []
            return

        # 2. Processing (Cleaning + Splitting)
        # We let Spacy handle the tokenization and sentence boundary detection.
        # We just strip whitespace around the whole doc first.
        doc = self.nlp(raw_text.strip())
        
        # 3. Populate AnalysisResult
        sentence_objects = []
        
        # doc.sents is a generator. We iterate through it.
        for idx, span in enumerate(doc.sents):
            text_segment = span.text.strip()
            
            if not text_segment:
                continue
            
            s_obj = SentenceScore(
                index=idx,
                text=text_segment,
                score=0.0,       # Default initialization
                embedding=None   # Will be filled by Embedder
            )
            sentence_objects.append(s_obj)

        result.sentences = sentence_objects
        logger.info(f"Preprocessor: Split article into {len(sentence_objects)} sentences.")
