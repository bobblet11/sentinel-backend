# washington_scraper.py
from bs4 import BeautifulSoup
from typing import Dict, Optional
import re
from ..base_parser import BaseParser
from urllib.parse import urlparse

class WashingtonPostScraper(BaseParser):
    def matches(self, url: str) -> bool:
        try:
            net = urlparse(url).netloc.lower()
            return "washingtonpost.com" in net or "feeds.washingtonpost.com" in net
        except Exception:
            return False

    def extract(self, soup: BeautifulSoup, url: str) -> Optional[Dict]:
        # WashingtonPost uses div[data-test-id="article-body"] or article tag
        container = soup.find("div", {"data-test-id": "article-body"}) or soup.find("article") or soup
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
            h1 = soup.find("h1")
            if h1:
                title = h1.get_text(strip=True)

        # author
        author = None
        author_meta = soup.find("meta", {"name": "author"})
        if author_meta and author_meta.get("content"):
            author = author_meta["content"].strip()
        if not author:
            # look for byline
            by = soup.find(class_=re.compile(r"(author|byline)", re.I))
            if by:
                author = by.get_text(strip=True)

        # date
        published_at = None
        meta_date = soup.find("meta", {"property": "article:published_time"}) or soup.find("meta", {"name": "date"})
        if meta_date and meta_date.get("content"):
            published_at = meta_date["content"].strip()
        if not published_at:
            t = soup.find("time")
            if t and t.get("datetime"):
                published_at = t["datetime"]

        return {"title": title, "text": text, "author": author, "published_at": published_at}
