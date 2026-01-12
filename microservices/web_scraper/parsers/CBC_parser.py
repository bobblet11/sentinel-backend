# nyt_scraper.py
import re
from typing import Dict, Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from microservices.web_scraper.parsers.base_parser import BaseParser, ParseResult


class CBCParser(BaseParser):
    def extract(self, soup: BeautifulSoup, article_url: str) -> Optional[ParseResult]:
        container = (
            soup.find("main") or soup.find("div", {"id": "app"}) or soup
        )
        self._remove_unwanted(container)

        paragraphs = container.find_all("p")
        text = self._clean_paragraphs(paragraphs)
        if not text:
            return None

        # Title
        title = None
        og = soup.find("meta", property="og:title")
        if og and og.get("content"):
            title = og["content"].strip()
        if not title:
            h1 = soup.find("h1", class_="detailHeadline") or soup.find("h1", class_="sclt-story-headline") or soup.find("h1")
            if h1:
                title = h1.get_text(strip=True)
        if not title and soup.title:
            title = soup.title.string      
        
                # Author & Date
        author = None
        published_at = None
        
        time_tag = soup.find("time")
        if time_tag:
            published_at = time_tag.get("datetime")
        
        # DOM
        if not author or not published_at:
            byline_div = soup.find("div", class_="byline") or soup.find("div", class_="bylineDetails") or soup.find("div", class_="story-credits")
            
            if byline_div:
                # Author
                if not author:
                    author_spans = byline_div.find_all("span", class_="authorText") or byline_div.find_all("a", href=re.compile("author"))
                    if author_spans:
                        author = ", ".join([a.get_text(strip=True) for a in author_spans]) 

                # Date Fallback
                if not published_at:
                    full_text = byline_div.get_text(" ", strip=True)
                    # Safe check before index
                    if "Posted:" in full_text:
                        try:
                            # Split by "Posted:" and take the part after it
                            published_at = full_text.split("Posted:", 1)[1].strip()
                        except IndexError:
                            pass
        if not title or not author or not published_at:
            print(f"[HARDCODED PARSE ERROR] something is not correct for {article_url}\n\t:text{text}\n\ttitle:{title}\n\tauthor:{author}\n\tpublished:{published_at}") 

        return ParseResult(text, title, author, published_at)
