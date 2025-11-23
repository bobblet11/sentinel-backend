import json
import re
from typing import Any, Dict, Optional

import trafilatura
from bs4 import BeautifulSoup

from .scraper_registry import ScraperRegistry


class ParseManager:
    """
    Robust HTML -> article parser which:
      1) Checks hardcoded scrapers (registry)
      2) Uses RSS metadata if provided (message-driven)
      3) Uses trafilatura
      4) Falls back to DOM paragraph extraction
    """

    def __init__(self):
        self.registry = ScraperRegistry()

    def parse_article_html(
        self,
        html: str,
        url: Optional[str] = None,
        rss_meta: Optional[Dict[str, Any]] = None,
    ) -> Dict:
        """
        html: raw HTML string
        url: optional; used to select hardcoded scrapers
        rss_meta: optional metadata from RSS (e.g., {'title':..., 'author':..., 'published':...})
        """
        if not html or len(html) < 20:
            raise ValueError("HTML content too short or empty during parsing")

        # 0) If RSS metadata provided and has full text, prefer that
        if rss_meta:
            out = {
                "title": rss_meta.get("title"),
                "text": rss_meta.get("content") or rss_meta.get("description"),
                "author": rss_meta.get("author") or rss_meta.get("creator"),
                "published_at": rss_meta.get("published") or rss_meta.get("pubDate"),
            }
            # If RSS contains full content, return
            if out.get("text") and len(out["text"].strip()) > 100:
                return out

        # 1) Site-specific scrapers (hardcoded)
        if url:
            try:
                hard = self.registry.extract_if_known(url, html)

                if hard and hard.get("text") and len(hard["text"].strip()) > 80:
                    # fill missing metadata from JSON-LD or OG if missing
                    if not hard.get("title"):
                        hard["title"] = self._extract_title(html)
                    if not hard.get("author"):
                        hard["author"] = self._extract_author(html)
                    if not hard.get("published_at"):
                        hard["published_at"] = self._extract_date(html)
                    return hard
            except Exception:
                # registry extraction failed , general extraction will be used
                pass

        # 2) Trafilatura
        text = self._extract_with_trafilatura(html)
        # 3) fallback if trafilatura failed or too short
        if not text or len(text.strip()) < 80:
            text = self._fallback_extract_text(html)

        # normalize
        text = self._clean_text(text)

        return {
            "title": self._extract_title(html),
            "text": text,
            "author": self._extract_author(html),
            "published_at": self._extract_date(html),
        }

    def _extract_with_trafilatura(self, html: str) -> Optional[str]:
        try:
            text = trafilatura.extract(
                html, include_comments=False, include_tables=False
            )
            if text:
                print("[ParseManager] Using Trafilatura extraction")
            return text
        except Exception:
            return None

    def _fallback_extract_text(self, html: str) -> str:
        soup = BeautifulSoup(html, "lxml")
        print("[ParseManager] Using fallback DOM extraction")

        # prefer article or main
        container = soup.find(["article", "main"]) or soup
        # remove elements likely to be noise
        for tag in container(
            [
                "script",
                "style",
                "noscript",
                "header",
                "footer",
                "svg",
                "meta",
                "aside",
                "nav",
                "iframe",
                "figure",
            ]
        ):
            try:
                tag.decompose()
            except Exception:
                pass
        # extract paragraph text only
        paragraphs = [
            p.get_text(strip=True)
            for p in container.find_all("p")
            if p.get_text(strip=True)
        ]
        return "\n\n".join(paragraphs)

    def _extract_title(self, html: str) -> Optional[str]:
        soup = BeautifulSoup(html, "lxml")
        if soup.title and soup.title.string:
            return soup.title.string.strip()
        og = soup.find("meta", property="og:title")
        if og and og.get("content"):
            return og["content"].strip()
        # JSON-LD
        jsonld_title = self._extract_jsonld_property(html, "headline")
        if jsonld_title:
            return jsonld_title.strip()
        h1 = soup.find("h1")
        if h1:
            return h1.get_text(strip=True)
        return None

    def _extract_author(self, html: str) -> Optional[str]:
        soup = BeautifulSoup(html, "lxml")
        patterns = [
            {"name": "meta", "attrs": {"name": "author"}},
            {"name": "meta", "attrs": {"property": "article:author"}},
            {"name": "meta", "attrs": {"property": "og:author"}},
        ]
        for p in patterns:
            tag = soup.find(p["name"], p["attrs"])
            if tag and tag.get("content"):
                return tag["content"]
        jsonld_author = self._extract_jsonld_property(html, "author")
        if jsonld_author:
            if isinstance(jsonld_author, dict):
                return jsonld_author.get("name")
            elif isinstance(jsonld_author, str):
                return jsonld_author
        byline = soup.find(class_=re.compile(r"(author|byline)", re.I))
        if byline:
            return byline.get_text(strip=True)
        return None

    def _extract_date(self, html: str) -> Optional[str]:
        soup = BeautifulSoup(html, "lxml")
        date_tags = [
            {"property": "article:published_time"},
            {"name": "pubdate"},
            {"name": "publishdate"},
            {"name": "timestamp"},
            {"property": "og:updated_time"},
        ]
        for attrs in date_tags:
            tag = soup.find("meta", attrs=attrs)
            if tag and tag.get("content"):
                return tag["content"]
        jsonld_date = self._extract_jsonld_property(html, "datePublished")
        if jsonld_date:
            return jsonld_date
        return None

    def _extract_jsonld_property(self, html: str, prop: str):
        soup = BeautifulSoup(html, "lxml")
        scripts = soup.find_all("script", type="application/ld+json")
        for s in scripts:
            try:
                data = json.loads(s.string)
                if isinstance(data, list):
                    for item in data:
                        if prop in item:
                            return item[prop]
                elif isinstance(data, dict) and prop in data:
                    return data[prop]
            except Exception:
                continue
        return None

    def _clean_text(self, text: str) -> str:
        if not text:
            return ""
        text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
        return text.strip()
