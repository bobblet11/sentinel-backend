from bs4 import BeautifulSoup
from bs4.element import Comment
from typing import Dict, Optional
import re

class BaseParser:
    """
    Abstract base for site-specific hardcoded scrapers.
    Implement `matches(url)` and `extract(soup, url)` in subclasses.
    """

    def matches(self, url: str) -> bool:
        # Return True if this scraper should handle `url`.
        raise NotImplementedError

    def extract(self, soup: BeautifulSoup, url: str) -> Optional[Dict]:
        """
        Extract title/text/author/published_at from a BeautifulSoup object.
        Must return a dict with at least 'text', and optionally 'title','author','published_at'.
        Return None or empty dict to indicate failure.
        """
        raise NotImplementedError

    @staticmethod
    def _clean_paragraphs(paragraphs):
        out = []
        for p in paragraphs:
            if not p:
                continue
            text = p.get_text(separator=" ", strip=True)
            # skip tiny fragments (ads, captions)
            if len(text) < 30:
                continue
            out.append(text)
        return "\n\n".join(out).strip()

    @staticmethod
    def _remove_unwanted(container):
        for tag in container(["script", "style", "noscript", "header", "footer", "svg", "meta", "aside", "nav", "iframe", "figure"]):
            try:
                tag.decompose()
            except Exception:
                pass
        # remove comments
        for c in container(text=lambda t: isinstance(t, Comment)):
            try:
                c.extract()
            except Exception:
                pass
