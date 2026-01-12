# nyt_scraper.py
import re
from typing import Dict, Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from microservices.web_scraper.parsers.base_parser import BaseParser, ParseResult

# New York Times


class CBSParser(BaseParser):
    def extract(self, soup: BeautifulSoup, article_url: str) -> Optional[ParseResult]:
        container = (
            soup.find("div", {"class":"container"}) or soup
        )
        self._remove_unwanted(container)

        paragraphs = container.find_all("p")
        text = self._clean_paragraphs(paragraphs)
        if not text:
            return None

        # title
        title = None
        og = soup.find("meta", property="og:title")
        if og and og.get("content"):
            title = og["content"].strip()
        if not title:
            h1 = soup.find("h1" , {"class" : "content__title"})
            if h1:
                title = h1.get_text(strip=True)
                
        if not title and soup.find("title"):
            title = soup.find("title").string  
        
        # --- Author & Date (Prioritize Meta, Fallback to DOM) ---
        author = None
        published_at = None
        
        # 1. Try Meta Tags first (cleanest)
        time_tag = soup.find("time")
        if time_tag:
            published_at = time_tag.get("datetime")
            
        # 2. Get from DOM
        if not author or not published_at:
            byline_div_author = soup.find("div", {"class": "byline__author__popover-btn__label underline-on-hover"})
            byline_div_published = soup.find("div", {"class": "content__meta content__meta--timestamp"})
            
            if byline_div_author:
                # --- DOM Author Extraction ---
                if not author:
                    # Authors are usually linked in <a> tags within the byline
                    full_byline_author_text = byline_div_author.get_text(" ", strip=True)
                
                    if "By" in full_byline_author_text:
                        full_byline_author_text = full_byline_author_text.replace("By", "").strip()
                    author = full_byline_author_text
            
            if byline_div_published:
                # --- DOM Date Extraction ---
                if not published_at:
                    # The date is just text inside a div, hard to target by class.
                    # Best approach is Regex on the text content of the whole byline.
                    full_byline_published_text = byline_div_published.get_text(" ", strip=True)
                    
                    # Pattern matches: Month DD, YYYY (e.g., December 28, 2025)
                    # We accept roughly any time format after the year
                    date_pattern = r"([A-Z][a-z]+ \d{1,2}, \d{4}(?:, \d{1,2}:\d{2} [AP]M)?)"
                    match = re.search(date_pattern, full_byline_published_text)
                    if match:
                        published_at = match.group(1)
        if not title or not author or not published_at:
            print(f"[HARDCODED PARSE ERROR] something is not correct for {article_url}\n\t:text{text}\n\ttitle:{title}\n\tauthor:{author}\n\tpublished:{published_at}") 

        return ParseResult(text, title, author, published_at)
