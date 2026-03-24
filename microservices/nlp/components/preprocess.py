import logging
import re
from typing import List

# Local imports
from microservices.nlp.models.base import NLPComponent
from common.models.api.redis_models import Article, NLPOptions, NLPResult, SentenceScore

logger = logging.getLogger(__name__)

class Preprocessor(NLPComponent):
    """
    "Universal Janitor" Preprocessor.
    
    Strategies applied:
    1. Regex Cleaning: Removes distinct artifacts (Dates, UI buttons, Footers) using strict patterns.
    2. Footer Cutoff: Stops processing the text entirely once footer keywords are detected.
    3. Linguistic Filtering: Uses Spacy's POS tagger to remove short lines (< 7 tokens) 
       that look like sentences but lack verbs (e.g., "Politics", "Frank Gardner").
    """
    def __init__(self, nlp=None):
        if nlp:
            self.nlp = nlp
        else:
            from microservices.nlp.config import model_manager

            self.nlp = model_manager.get("SPACY_SENT")

    def _clean_and_repair_structure(self, raw_text: str) -> str:
        """
        Phase 1: Regex Cleaning (The Janitor)
        Removes obvious garbage (UI, Dates, Footers) before Spacy sees it.
        """
        if not raw_text: return ""

        lines = raw_text.split('\n')
        cleaned_lines = []
        
        # --- STOP PATTERNS (The Footer Cutoff) ---
        # If we see these, the article is likely over. Stop reading immediately.
        footer_cutoff_pattern = re.compile(r'(?i)^('
            r'more from (the )?bbc|related (content|stories|topics)|up next|most popular|'
            r'have you read\?|more on geographies|license and republishing|content index|'
            r'bbc\.com help|privacy policy|about us|follow .* on|sign up for'
        r')')
        
        # --- KILL LISTS (Regex Filters) ---
        # 1. Time & Meta: Matches "10 hrs ago", "Updated 1 min ago", "7 MIN READ"
        time_meta_pattern = re.compile(r'(?i)^('
            r'\d+\s+(hour|minute|day|second|hr|min)s?\s+ago|'
            r'updated\s+.*|'
            r'\d+\s+min\s+read|'
            r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{1,2},?\s+\d{4}'
        r')')

        # 2. Credits & Sources: Matches "Getty Images", "Analysis by", "Image: ..."
        credits_pattern = re.compile(r'(?i)^('
            r'(image|photo|source|graphic|credits?):|'
            r'(left|right|top|bottom):|'
            r'analysis by|'
            r'this article is part of:|'
            r'unknown\.|'
            r'getty images|epa|afp|ugc|reuters|ap|copyright|davidoff studios'
        r')')

        # 3. UI Elements: Matches "Sign In", "Share", "Menu"
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

        # 4. Bylines: Matches "By [Name]" or "Correspondent"
        byline_pattern = re.compile(r'(?i)^('
            r'by\s+[A-Z][a-z]+\s+[A-Z][a-z]+|'
            r'.*correspondent.*|'
            r'writer,.*'
        r')')

        for line in lines:
            line = line.strip()
            
            # Basic Filtering
            if not line: continue 
            if len(line) < 4: continue # Catches very short noise like "EPA."
            
            # --- PHASE 2: CUTOFF CHECK ---
            if footer_cutoff_pattern.search(line):
                # Stop processing the rest of the file
                break

            # --- PHASE 3: REGEX FILTERING ---
            if ui_pattern.search(line): continue
            if time_meta_pattern.search(line): continue
            if credits_pattern.search(line): continue
            if byline_pattern.search(line) and len(line) < 50: continue

            # --- PHASE 4: STRUCTURAL REPAIR ---
            # If a line is a header/claim (no punctuation), force a period.
            # This ensures Spacy splits it from the next line.
            if line[-1] not in ".?!:;\"'":
                line += "."
                
            cleaned_lines.append(line)
            
        return " ".join(cleaned_lines)

    def run(self, article: Article, result: NLPResult, options: NLPOptions) -> None:
        # 1. Regex Cleaning
        raw_text = getattr(article, 'text', getattr(article, 'content', ""))
        clean_text = self._clean_and_repair_structure(raw_text)
        
        if not clean_text:
            logger.warning("Preprocessor: Text was empty after cleaning.")
            result.sentences = []
            return

        # 2. Spacy Analysis (Tokenization + POS Tagging)
        doc = self.nlp(clean_text)
        
        sentence_objects = []
        for idx, span in enumerate(doc.sents):
            text_segment = span.text.strip()
            
            # --- PHASE 5: LINGUISTIC FILTER ---
            # If a sentence is short (< 7 tokens), we strictly check its grammar.
            token_count = len(span)
            
            if token_count < 7:
                # Rule A: Keep Questions (e.g. "What next?") even if they lack verbs
                if "?" in text_segment:
                    pass 
                
                # Rule B: If it's not a question, it MUST have a Verb (VERB) or Auxiliary Verb (AUX)
                # This kills: "Pablo Uchoa." (PROPN), "Geographies in Depth." (NOUN)
                # This keeps: "He died." (VERB), "It was chaos." (AUX)
                else:
                    has_verb = any(token.pos_ in ["VERB", "AUX"] for token in span)
                    if not has_verb:
                        continue # Skip this sentence

            # Create sentence object
            s_obj = SentenceScore(
                index=idx, 
                text=text_segment, 
                score=0.0, 
                embedding=None
            )
            sentence_objects.append(s_obj)

        result.sentences = sentence_objects
        logger.info(f"Preprocessor: Cleaned & Split. Result: {len(sentence_objects)} sentences.")
