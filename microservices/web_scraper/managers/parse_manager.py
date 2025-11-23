import json
import re
from typing import Any, Dict, Optional

import trafilatura
from bs4 import BeautifulSoup

from microservices.web_scraper.managers.parser_registry_manager import (
    ParserRegistryManager,
)
from microservices.web_scraper.parsers.base_parser import BaseParser


class ParseManager:
    """
    Robust HTML -> article parser which:
      1) Checks hardcoded scrapers (registry)
      2) Uses RSS metadata if provided (message-driven)
      3) Uses trafilatura
      4) Falls back to DOM paragraph extraction
    """

    def __init__(self):
        self.hardcoded_parser_registry = ParserRegistryManager()
        self.name = type(self).__name__

    def parse_article_html(
        self,
        html: str,
        url: Optional[str] = None,
        rss_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict:

        if not html or len(html) < 20:
            raise ValueError(
                f"[{self.name}] HTML content too short or empty during parsing"
            )

        # 0) If RSS metadata provided and has full text, prefer that
        if rss_metadata:
            text_content: str = rss_metadata.get("content") or rss_metadata.get(
                "description"
            )
            rss_metadata_is_sufficient: bool = (
                text_content and len(text_content.strip()) > 100
            )

            if rss_metadata_is_sufficient:
                print(f"[{self.name}] using RSS metadata")
                output: Dict[str, Any] = {
                    "title": rss_metadata.get("title"),
                    "text": rss_metadata.get("content")
                    or rss_metadata.get("description"),
                    "author": rss_metadata.get("author") or rss_metadata.get("creator"),
                    "published_at": rss_metadata.get("published")
                    or rss_metadata.get("pubDate"),
                }
                return output

        # 1) Hardcoded Scraper
        if url:
            try:
                output: Dict[str, Any] = self._extract_with_hardcoded_parser(url, html)
                text_content: str = rss_metadata.get("content") or rss_metadata.get(
                    "description"
                )
                hardcoded_parser_is_sufficient: bool = (
                    text_content and len(text_content.strip()) > 80
                )

                if hardcoded_parser_is_sufficient:
                    print(f"[{self.name}] using hardcoded parser")
                    # fill missing metadata from JSON-LD or OG if missing
                    if not output.get("title"):
                        output["title"] = self._extract_title(html)
                    if not output.get("author"):
                        output["author"] = self._extract_author(html)
                    if not output.get("published_at"):
                        output["published_at"] = self._extract_date(html)
                    return output

            except Exception:
                pass

        # 2) Trafilatura
        text_content = self._extract_with_trafilatura(html)
        trafilatura_is_sufficient: bool = (
            text_content and len(text_content.strip()) > 80
        )

        # 3) fallback if trafilatura failed or too short
        if not trafilatura_is_sufficient:
            print(f"[{self.name}] using fallback method")
            text_content = self._fallback_extract_text(html)

        print(f"[{self.name}] using trafilatura")
        text_content = self._clean_text(text_content)

        return {
            "title": self._extract_title(html),
            "text": text_content,
            "author": self._extract_author(html),
            "published_at": self._extract_date(html),
        }

    def _extract_with_hardcoded_parser(self, url: str, html: str) -> Optional[Dict]:
        if not url or not html:
            return None

        hardcoded_parser: Optional[BaseParser] = (
            self.hardcoded_parser_registry.find_matching_parser(url)
        )

        if not hardcoded_parser:
            return None

        soup = BeautifulSoup(html, "lxml")
        return hardcoded_parser.extract(soup, url)

    def _extract_with_trafilatura(self, html: str) -> Optional[str]:
        try:
            text_content = trafilatura.extract(
                html, include_comments=False, include_tables=False
            )
            return text_content
        except Exception:
            return None

    def _fallback_extract_text(self, html: str) -> str:
        soup = BeautifulSoup(html, "lxml")
        container = soup.find(["article", "main"]) or soup
        noisy_tags_to_remove = container(
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
        )

        for tag in noisy_tags_to_remove:
            try:
                tag.decompose()
            except Exception:
                pass

        paragraphs = [
            p.get_text(strip=True)
            for p in container.find_all("p")
            if p.get_text(strip=True)
        ]

        joined_paragraphs = "\n\n".join(paragraphs)
        return joined_paragraphs

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

        for pattern in patterns:
            tag = soup.find(pattern["name"], pattern["attrs"])

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

        for script in scripts:
            try:
                data = json.loads(script.string)
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
