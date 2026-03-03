import logging
import spacy
import re
from typing import List

# Local imports
from microservices.nlp.models.base import NLPComponent
from common.models.api.redis_models import Article, NLPOptions, NLPResult, SentenceScore
from microservices.nlp.config import PREPROCESS_MIN_TOKENS, PHOTO_CREDIT_MAX_LEN

logger = logging.getLogger(__name__)

class Preprocessor(NLPComponent):
    """
    "Universal Janitor" Preprocessor.
    
    Strategies applied:
    1. Regex Cleaning: Removes distinct artifacts (Dates, UI buttons, Footers) using strict patterns.
    2. Footer Cutoff: Stops processing the text entirely once footer keywords are detected.
    3. Linguistic Filtering: Uses Spacy's POS tagger to remove short lines (< 7 tokens) 
       that look like sentences but lack verbs (e.g., "Politics", "Frank Gardner").

    Returns sentences via a local list; does NOT write to result.sentences.
    """
    def __init__(self):
        logger.info("Preprocessor: Loading Spacy 'en_core_web_sm' model...")
        try:
            # We disable NER and Lemmatizer as they are handled by specialized downstream components
            self.nlp = spacy.load("en_core_web_sm", disable=["ner", "lemmatizer"])
        except OSError:
            logger.error("Spacy model not found. Run: python -m spacy download en_core_web_sm")
            raise

        # Compiled once at init; used by both line-level and sentence-level filters.
        self._photo_credit_re = re.compile(
            r'(?i)\b(getty|reuters|afp|ntb|epa|ugc|ap|bbc|pool|handout|'
            r'shutterstock|alamy|corbis|zuma|sipa|nurphoto|xinhua|'
            r'press association|pa images|sky news|itv|abc news)\b'
        )

    def _clean_and_repair_structure(self, raw_text: str) -> str:
        if not raw_text: 
            return ""

        lines = raw_text.split('\n')
        cleaned_lines = []
        
        # Stop processing entirely when these markers appear
        footer_cutoff_pattern = re.compile(r'(?i)^('
            r'more from (the )?bbc|related (content|stories|topics)|up next|most popular|'
            r'have you read\?|more on geographies|license and republishing|content index|'
            r'bbc\.com help|privacy policy|about us|follow .* on|sign up for'
        r')')
        
        # Filter patterns for metadata and UI elements
        time_meta_pattern = re.compile(r'(?i)^('
            r'\d+\s+(hour|minute|day|second|hr|min)s?\s+ago|'
            r'updated\s+.*|'
            r'\d+\s+min\s+read|'
            r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{1,2},?\s+\d{4}'
        r')')

        credits_pattern = re.compile(r'(?i)^('
            r'(image|photo|source|graphic|credits?):|'
            r'(left|right|top|bottom):|'
            r'analysis by|'
            r'this article is part of:|'
            r'unknown\.|'
            r'getty images|epa|afp|ugc|reuters|ap|copyright|davidoff studios'
        r')')

        ui_pattern = re.compile(r'(?i)^('
            r'register|sign in|log in|'
            r'skip to.*|'
            r'share|save|follow|subscribe|'
            r'menu|home|news|sport|weather|'
            r'listen to .* read this article|'
            r'loading\.\.\.|'
            r'create a free account|'
            r'terms of use'
        r')')

        byline_pattern = re.compile(r'(?i)^('
            r'by\s+[A-Z][a-z]+\s+[A-Z][a-z]+|'
            r'.*correspondent.*|'
            r'writer,.*'
        r')')

        # Matches photo/image attribution lines of the form
        # "Name/Agency/Agency." or "Agency/Getty Images." — these are
        # not sentences; they are short, slash-separated, and contain
        # at least one known media/photo agency token.
        photo_credit_pattern = self._photo_credit_re

        for line in lines:
            line = line.strip()
            if not line: 
                continue 
            if len(line) < 4: 
                continue
            
            if footer_cutoff_pattern.search(line): 
                break
            
            if ui_pattern.search(line): 
                continue
            if time_meta_pattern.search(line): 
                continue
            if credits_pattern.search(line): 
                continue

            # Drop short slash-separated photo attribution lines
            # e.g. "Jeff Overs/BBC/Reuters." or "Ole Berg-Rusten/NTB/AFP/Getty Images."
            # Guard: only drop if the line also contains NO verb — real claims that
            # mention these agencies inline (e.g. "Reuters reported that...") always
            # have at least one VERB/AUX token and are preserved.
            if '/' in line and len(line) < PHOTO_CREDIT_MAX_LEN and photo_credit_pattern.search(line):
                has_verb = any(t.pos_ in ("VERB", "AUX") for t in self.nlp(line))
                if not has_verb:
                    continue
            
            # Filter bylines unless they are unusually long (potential sentences)
            if byline_pattern.search(line) and len(line) < 50: 
                continue
            
            # Repair missing sentence endings
            if line[-1] not in ".?!:;\"'":
                line += "."
            
            cleaned_lines.append(line)
            
        return " ".join(cleaned_lines)

    def run(self, article: Article, result: NLPResult, options: NLPOptions) -> List[SentenceScore]:
        """
        Cleans and tokenizes the article text into local SentenceScore objects.
        """
        raw_text = getattr(article, 'text', getattr(article, 'content', ""))
        clean_text = self._clean_and_repair_structure(raw_text)
        
        if not clean_text:
            logger.warning("Preprocessor: Text was empty after cleaning.")
            return []

        doc = self.nlp(clean_text)
        
        sentence_objects = []
        for idx, span in enumerate(doc.sents):
            text_segment = span.text.strip()
            token_count = len(span)
            
            # Linguistic filtering for short fragments
            if token_count < PREPROCESS_MIN_TOKENS:
                if "?" in text_segment:
                    pass # Questions are often valid claims/segments
                else:
                    # Drop short lines that lack a verb (likely labels or titles)
                    has_verb = any(token.pos_ in ["VERB", "AUX"] for token in span)
                    if not has_verb:
                        continue

            # Sentence-level photo credit guard (catches credits not separated
            # by newlines in the raw article, which the line-level filter misses).
            # Same rule: slash-separated, agency token present, no verb.
            if ('/' in text_segment
                    and len(text_segment) < PHOTO_CREDIT_MAX_LEN
                    and self._photo_credit_re.search(text_segment)
                    and not any(tok.pos_ in ("VERB", "AUX") for tok in span)):
                continue

            s_obj = SentenceScore(
                index=idx,
                text=text_segment,
                score=0.0,
                embedding=None
            )
            sentence_objects.append(s_obj)

        logger.info(f"Preprocessor: Cleaned & Split. Result: {len(sentence_objects)} sentences.")
        return sentence_objects