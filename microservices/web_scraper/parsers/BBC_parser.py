# nyt_scraper.py
import re
from typing import Dict, Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from microservices.web_scraper.parsers.base_parser import BaseParser, ParseResult

class BBCParser(BaseParser):
    def extract(self, soup: BeautifulSoup, article_url: str) -> Optional[ParseResult]:
        container = (
            soup.find("main") or soup.find("article") or soup
        )
        self._remove_unwanted(container)
        
        # BBC specific cleaning
        for tag in container.find_all(class_=re.compile(r"Metadata|Share|Related")):
            tag.decompose()

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
            h1 = soup.find("h1")
            if h1:
                title = h1.get_text(strip=True)
        if not title and soup.title:
            title = soup.title.string    

        # Author (BBC often doesn't list individual authors, just 'BBC News')
        author = None
        meta_author = soup.find("meta", {"property": "article:author"}) or soup.find("meta", {"name": "author"})
        if meta_author and meta_author.get("content"):
            author = meta_author["content"]

        # Date
        published_at = None
        # Try standard OGP first
        meta_date = soup.find("meta", {"property": "article:published_time"}) or soup.find("time")
        if meta_date:
            published_at = meta_date.get("content") or meta_date.get("datetime")
        
        if not title or not author or not published_at:
            print(f"[HARDCODED PARSE ERROR] something is not correct for {article_url}\n\t:text{text}\n\ttitle:{title}\n\tauthor:{author}\n\tpublished:{published_at}") 

        return ParseResult(text, title, author, published_at)
