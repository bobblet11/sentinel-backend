# nyt_scraper.py
import re
from typing import Dict, Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from microservices.web_scraper.parsers.base_parser import BaseParser

# New York Times


class NytParser(BaseParser):
    def matches(self, url: str) -> bool:
        try:
            net = urlparse(url).netloc.lower()
            return "nytimes.com" in net or "rss.nytimes.com" in net
        except Exception:
            return False

    def extract(self, soup: BeautifulSoup, url: str) -> Optional[Dict]:
        # NYTimes often uses <section name="articleBody"> or article > div[data-testid="article-body"]
        container = (
            soup.find("section", {"name": "articleBody"})
            or soup.find("section", {"itemprop": "articleBody"})
            or soup.find("article")
        )
        if not container:
            container = soup

        self._remove_unwanted(container)

        paragraphs = container.find_all("p")
        text = self._clean_paragraphs(paragraphs)
        if not text:
            return None

        # title heuristics: meta og:title -> JSON-LD -> h1
        title = None
        og = soup.find("meta", property="og:title")
        if og and og.get("content"):
            title = og["content"].strip()
        if not title:
            h1 = soup.find("h1")
            if h1:
                title = h1.get_text(strip=True)

        # author heuristics: meta name=byl (NYT uses 'by' lines)
        author = None
        meta_by = soup.find("meta", {"name": "byl"})
        if meta_by and meta_by.get("content"):
            author = meta_by["content"].strip()
        if not author:
            # common class byline
            by = soup.find(class_=re.compile(r"(byline|css-[\w-]*Byline)", re.I))
            if by:
                author = by.get_text(strip=True)

        # published date
        published_at = None
        meta_date = soup.find(
            "meta", {"property": "article:published_time"}
        ) or soup.find("meta", {"name": "ptime"})
        if meta_date and meta_date.get("content"):
            published_at = meta_date["content"].strip()
        # fallback to <time datetime=...>
        if not published_at:
            t = soup.find("time")
            if t and t.get("datetime"):
                published_at = t["datetime"]

        return {
            "title": title,
            "text": text,
            "author": author,
            "published_at": published_at,
        }
