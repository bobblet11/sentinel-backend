# nyt_scraper.py
import re
from typing import Dict, Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from microservices.web_scraper.parsers.base_parser import BaseParser, ParseResult


class EuronewsParser(BaseParser):
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
            h1 = soup.find("h1" , {"class" : "c-article-redesign-title"})
            if h1:
                title = h1.get_text(strip=True)
                
        if not title and soup.find("title"):
            title = soup.find("title").string  
        
        # --- Author & Date (Prioritize Meta, Fallback to DOM) ---
        author = None
        published_at = None
        
        # 1. Try Meta Tags first (cleanest)
        
        meta_author = soup.find("meta", {"name": "article:author"}) or soup.find("meta", {"property": "article:author"})

        if meta_author and meta_author.get("content"):
            author = meta_author["content"]
            
        time_tag = soup.find("time")
        if time_tag:
            published_at = time_tag.get("datetime")
        
        if published_at:
            published_at = published_at.replace(" ", "T", 1)
            
        # 2. Get from DOM
        if not author or not published_at:
            byline_div_author = soup.find("div", {"class": "c-article-contributors"})
            byline_div_published = soup.find("div", {"class": "c-article-publication-date"})
            
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
                    if "Published on" in full_byline_published_text:
                        full_byline_published_text = full_byline_published_text.replace("Published on", "").strip()
                    published_at = full_byline_published_text
        if not title or not author or not published_at:
            print(f"[HARDCODED PARSE ERROR] something is not correct for {article_url}\n\t:text{text}\n\ttitle:{title}\n\tauthor:{author}\n\tpublished:{published_at}") 
     
        return ParseResult(text, title, author, published_at)
