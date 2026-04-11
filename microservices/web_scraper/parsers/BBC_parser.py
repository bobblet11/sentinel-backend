# nyt_scraper.py
import json
import re
from typing import Dict, Optional

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

        # Author
        author = None

        # BBC meta / JSON-LD / byline fallbacks
        meta_author_candidates = [
            soup.find("meta", {"property": "cXenseParse:author"}),
            soup.find("meta", {"name": "author"}),
            soup.find("meta", {"property": "article:author"}),
            soup.find("meta", {"property": "og:author"}),
        ]

        for tag in meta_author_candidates:
            if tag and tag.get("content"):
                content = tag["content"].strip()
                if content and not content.startswith("http"):
                    author = content
                    break

        if not author:
            # Common BBC byline patterns
            byline_candidates = [
                soup.select_one('[data-testid*="byline"]'),
                soup.select_one('[class*="byline"]'),
                soup.select_one('[class*="Contributor"]'),
            ]
            for node in byline_candidates:
                if node:
                    text = node.get_text(" ", strip=True)
                    if text and not text.startswith("http"):
                        text = re.sub(r"^By\s+", "", text, flags=re.I).strip()
                        author = text
                        break

        # Date
        published_at = None

        # 1) JSON-LD first
        for script in soup.find_all("script", type="application/ld+json"):
            if not script.string:
                continue
            try:
                data = json.loads(script.string)
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    value = item.get("datePublished") or item.get("dateCreated")
                    if value:
                        published_at = str(value).strip()
                        break
                if published_at:
                    break
            except Exception:
                continue

        # 2) Meta tags
        if not published_at:
            date_candidates = [
                soup.find("meta", {"property": "article:published_time"}),
                soup.find("meta", {"property": "article:modified_time"}),
                soup.find("meta", {"property": "og:updated_time"}),
                soup.find("meta", {"name": "pubdate"}),
            ]

            for tag in date_candidates:
                if not tag:
                    continue
                value = tag.get("content") or tag.get("datetime")
                if value:
                    published_at = value.strip()
                    break

        # 3) <time> tag
        if not published_at:
            time_tag = soup.find("time")
            if time_tag:
                published_at = time_tag.get("datetime") or time_tag.get_text(" ", strip=True)
                if published_at:
                    published_at = published_at.strip()
        if not title or not author or not published_at:
            print(f"[BBCParser WARNING] Partial parse for {article_url} | title={bool(title)} author={bool(author)} published={bool(published_at)}")

        return ParseResult(text, title, author, published_at)
