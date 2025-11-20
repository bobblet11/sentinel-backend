import json
import re
from typing import Optional, Dict

import trafilatura
from bs4 import BeautifulSoup
from bs4.element import Comment


class ParseManager:
    """
    Lightweight HTML → article text parser.

    Extraction strategy:
    1. Try Trafilatura (best-case full article extraction)
    2. Fallback: manually extract paragraphs from <article>/<main>
    3. Pull metadata (title, author, published date) from common tags/JSON-LD
    """

    def parse_article_html(self, html: str) -> Dict:
        # Main entry point. Takes raw HTML and returns a structured article dict.
        if not html or len(html) < 20:
            raise ValueError("HTML content too short or empty during parsing")

        title = self._extract_title(html)
        text = self._extract_with_trafilatura(html)

        # If Trafilatura fails or produces too little content, fallback to manual parsing
        if not text or len(text.strip()) < 80:
            text = self._fallback_extract_text(html)

        text = self._clean_text(text)

        return {
            "title": title,
            "text": text,
            "author": self._extract_author(html),
            "published_at": self._extract_date(html),
        }

    # ---------------------------------------------------------------------
    # Trafilatura extraction
    # ---------------------------------------------------------------------
    def _extract_with_trafilatura(self, html: str) -> Optional[str]:
        try:
            return trafilatura.extract(
                html,
                include_comments=False,
                include_tables=False,
            )
        except Exception:
            return None

    # ---------------------------------------------------------------------
    # DOM-based fallback extraction
    # ---------------------------------------------------------------------
    def _fallback_extract_text(self, html: str) -> str:
        soup = BeautifulSoup(html, "lxml")

        # Prefer structured containers first
        container = soup.find(["article", "main"]) or soup

        # Remove junk / non-content elements
        for tag_name in ["script", "style", "noscript", "header", "footer",
                         "svg", "meta", "aside", "nav", "iframe", "figure"]:
            for tag in container.find_all(tag_name):
                tag.decompose()

        # Remove HTML comments
        for element in container(text=lambda t: isinstance(t, Comment)):
            element.extract()

        # Extract visible paragraph text
        paragraphs = []
        for p in container.find_all("p"):
            text = p.get_text(strip=True)
            if text:
                paragraphs.append(text)

        return "\n\n".join(paragraphs)

    # ---------------------------------------------------------------------
    # Title extraction
    # ---------------------------------------------------------------------
    def _extract_title(self, html: str) -> Optional[str]:
        soup = BeautifulSoup(html, "lxml")

        # <title>
        if soup.title and soup.title.string:
            return soup.title.string.strip()

        # OpenGraph
        og = soup.find("meta", property="og:title")
        if og and og.get("content"):
            return og["content"].strip()

        # JSON-LD headline
        jsonld_title = self._extract_jsonld_property(html, "headline")
        if jsonld_title:
            return jsonld_title.strip()

        # Fallback: first H1
        h1 = soup.find("h1")
        if h1:
            return h1.get_text(strip=True)

        return None

    # ---------------------------------------------------------------------
    # Author extraction
    # ---------------------------------------------------------------------
    def _extract_author(self, html: str) -> Optional[str]:
        soup = BeautifulSoup(html, "lxml")

        # Meta tags
        candidates = [
            {"name": "meta", "attrs": {"name": "author"}},
            {"name": "meta", "attrs": {"property": "article:author"}},
            {"name": "meta", "attrs": {"property": "og:author"}},
        ]
        for c in candidates:
            el = soup.find(c["name"], c["attrs"])
            if el and el.get("content"):
                return el["content"].strip()

        # JSON-LD
        jsonld_author = self._extract_jsonld_property(html, "author")
        if isinstance(jsonld_author, dict):
            return jsonld_author.get("name")
        if isinstance(jsonld_author, str):
            return jsonld_author

        # Heuristic fallback
        byline = soup.find(class_=re.compile(r"(author|byline)", re.I))
        if byline:
            return byline.get_text(strip=True)

        return None

    # ---------------------------------------------------------------------
    # Date extraction
    # ---------------------------------------------------------------------
    def _extract_date(self, html: str) -> Optional[str]:
        soup = BeautifulSoup(html, "lxml")

        # Common meta variations
        date_fields = [
            {"property": "article:published_time"},
            {"name": "pubdate"},
            {"name": "publishdate"},
            {"name": "timestamp"},
            {"property": "og:updated_time"},
        ]
        for attrs in date_fields:
            tag = soup.find("meta", attrs=attrs)
            if tag and tag.get("content"):
                return tag["content"]

        # JSON-LD datePublished
        return self._extract_jsonld_property(html, "datePublished")

    # ---------------------------------------------------------------------
    # JSON-LD helper
    # ---------------------------------------------------------------------
    def _extract_jsonld_property(self, html: str, prop: str):
        soup = BeautifulSoup(html, "lxml")

        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string)

                # JSON-LD can be list or dict
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and prop in item:
                            return item[prop]
                elif isinstance(data, dict) and prop in data:
                    return data[prop]

            except Exception:
                continue

        return None

    # ---------------------------------------------------------------------
    # Clean text
    # ---------------------------------------------------------------------
    def _clean_text(self, text: str) -> str:
        # Collapse excessive blank lines
        text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
        return text.strip()
