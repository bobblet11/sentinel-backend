import logging
import spacy
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
    def __init__(self):
        logger.info("Preprocessor: Loading Spacy 'en_core_web_sm' model...")
        try:
            # CRITICAL CHANGE: We REMOVED 'tagger' and 'attribute_ruler' from the disable list.
            # We need them enabled so Spacy can identify Verbs vs Nouns.
            self.nlp = spacy.load("en_core_web_sm", disable=["ner", "lemmatizer"])
        except OSError:
            logger.error("Spacy model not found. Run: python -m spacy download en_core_web_sm")
            raise

    def _clean_and_repair_structure(self, raw_text: str) -> str:
        """
        Phase 1: Regex Cleaning (The Janitor)
        Removes obvious garbage (UI, Dates, Footers) before Spacy sees it.
        """
        if not raw_text: return ""

        lines = raw_text.split('\n')
        cleaned_lines = []
        seen_lines = set()
        
        # --- STOP PATTERNS (The Footer Cutoff) ---
        # If we see these, the article is likely over. Stop reading immediately.
        footer_cutoff_pattern = re.compile(r'(?i)^('
            r'more from (the )?bbc|related (content|stories|topics)|up next|most popular|'
            r'have you read\?|more on geographies|license and republishing|content index|'
            r'bbc\.com help|privacy policy|about us|follow .* on|sign up for|'
            r'explore more on these topics|most viewed|reuse this content|'
            r'back to top|all topics|all writers|newsletters|digital newspaper archive|'
            r'advertise with us|work with us|accessibility settings|'
            r'understanding what is happening in the middle east is more important than ever|'
            r'we rely on the generosity of our readers|'
            r'choosing to back us on a monthly basis makes the most impact|'
            r'our standards: the thomson reuters trust principles|'
            r'suggested topics:|read next|site index|about reuters|stay informed|'
            r'follow us|lseg products|workspace|data catalogue|world-check|'
            r'information you can trust|all quotes delayed a minimum of 15 minutes|'
            r'copyright|terms & conditions|privacy|manage cookies|'
            r'reuters, the news and media division of thomson reuters'
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
            r'support (the )?guardian|support us|continue|remind me in .*|'
            r'view image in fullscreen|prefer the guardian on google|'
            r'report ad|loading ad|advertisement.*|'
            r'exclusive news, data and analytics for financial market professionals|'
            r'listen to .* read this article|'
            r'loading\.\.\.|'
            r'create a free account|'
            r'terms of use'
        r')')

        # Catch encoded/debug fragments and broken telemetry tails.
        junk_pattern = re.compile(r'(?i)^('
            r'in/[a-z0-9/_-]{6,}|'
            r'more data|summary reportdiagnosisdensity|'
            r'\d{1,4}\s+\d{1,4}\s+n/?a|'
            r'\[\d+/\d+\].*|item\s+\d+\s+of\s+\d+.*|'
            r'\d+\s+seconds\s+of\s+\d+\s+seconds.*volume\s*\d+%'
        r')')

        # 4. Bylines: Matches "By [Name]" or "Correspondent"
        byline_pattern = re.compile(r'(?i)^('
            r'by\s+[A-Z][a-z]+\s+[A-Z][a-z]+|'
            r'.*correspondent.*|'
            r'writer,.*'
        r')')

        # Reuters metadata and utility lines that are not article body.
        reuters_meta_pattern = re.compile(r'(?i)^('
            r'march\s+\d{1,2},\s+\d{4}.*(gmt|est|edt|utc|am|pm).*(updated|ago)?|'
            r'reporting by .*; writing by .*; editing by .*|'
            r'purchase licensing rights|'
            r'thomson reuters|'
            r'category|'
            r'opens new tab|'
            r'download the app \(ios\)|download the app \(android\)|'
            r'reuters leadership|reuters fact check|reuters diversity report|'
            r'media center|advertise with us|reuters news agency|'
            r'brand attribution guidelines|reuters and ai|'
            r'data disclosure and sources|site feedback'
        r')')

        for line in lines:
            line = line.strip()
            line = re.sub(r'\s+', ' ', line)
            
            # Basic Filtering
            if not line:
                continue
            if len(line) < 4:
                continue # Catches very short noise like "EPA."

            # Skip exact duplicates which are common in scraped nav blocks.
            lowered = line.lower()
            if lowered in seen_lines:
                continue
            seen_lines.add(lowered)
            
            # --- PHASE 2: CUTOFF CHECK ---
            if footer_cutoff_pattern.search(line):
                # Stop processing the rest of the file
                break

            # --- PHASE 3: REGEX FILTERING ---
            if ui_pattern.search(line): continue
            if time_meta_pattern.search(line): continue
            if credits_pattern.search(line): continue
            if byline_pattern.search(line) and len(line) < 50: continue
            if junk_pattern.search(line): continue
            if reuters_meta_pattern.search(line): continue

            # Reuters often inserts newsletter and summary/companies utility blocks.
            if line.lower() in {"summary", "companies", "latest", "archive", "browse", "videos", "pictures", "graphics", "podcasts", "authors", "home"}:
                continue

            # Drop pure section menus and taxonomy lists (e.g., "Business", "Economics").
            if re.fullmatch(r"[A-Za-z& ]{3,30}", line):
                token_count = len(line.split())
                if token_count <= 3:
                    continue

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
