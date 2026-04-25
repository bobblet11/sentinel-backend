from dataclasses import dataclass
from typing import Optional

from bs4 import BeautifulSoup
from bs4.element import Comment


@dataclass
class ParseResult:
    text: str
    title: Optional[str]
    author: Optional[str]
    published_at: Optional[str]
    
    def __getitem__(self, key):
        return getattr(self, key, None)
    
    def __setitem__(self, key, value):
        if hasattr(self, key):
            setattr(self, key, value)
        else:
            raise KeyError(f"{key} is not a valid field")

class BaseParser:
    """
    Abstract base for site-specific hardcoded scrapers.
    Implement `extract(soup, url)` in subclasses.
    """

    def extract(self, soup: BeautifulSoup, url: str) -> Optional[ParseResult]:
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

        for c in container(text=lambda t: isinstance(t, Comment)):
            try:
                c.extract()
            except Exception:
                pass
