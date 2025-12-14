from typing import Dict, Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from microservices.web_scraper.parsers.base_parser import BaseParser

# Wall Street Journal


class WsjParser(BaseParser):
    def matches(self, url: str) -> bool:
        try:
            net = urlparse(url).netloc.lower()
            return (
                "wsj.com" in net
                or "dowjones" in net
                or "feeds.content.dowjones.io" in net
            )
        except Exception:
            return False

    def extract(self, soup: BeautifulSoup, url: str) -> Optional[Dict]:
        # WSJ uses article tags and .wsj-article-body etc.
        container = (
            soup.find("div", {"id": "article-content"}) or soup.find("article") or soup
        )
        self._remove_unwanted(container)

        # paragraphs (some WSJ pages use .article-content p)
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
        meta_author = soup.find("meta", {"name": "author"})
        if meta_author and meta_author.get("content"):
            author = meta_author["content"]

        # date
        published_at = None
        meta_date = soup.find(
            "meta", {"property": "article:published_time"}
        ) or soup.find("time")
        if meta_date and meta_date.get("content"):
            published_at = meta_date["content"]
        elif meta_date and meta_date.get("datetime"):
            published_at = meta_date["datetime"]

        return {
            "title": title,
            "text": text,
            "author": author,
            "published_at": published_at,
        }
