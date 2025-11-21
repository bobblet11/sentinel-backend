# scraper_registry.py
from typing import Optional
from bs4 import BeautifulSoup
from .base_parser import BaseParser

from .scrapers.nyt_scraper import NYTScraper
from .scrapers.washington_scraper import WashingtonPostScraper
from .scrapers.wsj_scraper import WSJScraper


class ScraperRegistry:
    """
    Registry of site-specific scrapers.
    Call get_scraper_for_url(url) to retrieve a matching scraper (or None).
    """

    def __init__(self):
        # Site-specific scrapers here in priority order
        self.scrapers = [
            NYTScraper(),
            WashingtonPostScraper(),
            WSJScraper(),
        ]

    def get_scraper_for_url(self, url: str) -> Optional[BaseParser]:
        for s in self.scrapers:
            try:
                if s.matches(url):
                    print("[ScraperRegistry] Using scraper:", s.__class__.__name__)
                    return s
            except Exception:
                # protect registry from broken scraper code
                continue
        return None

    def extract_if_known(self, url: str, html: str):
        if not url:
            return None
        scraper = self.get_scraper_for_url(url)
        if not scraper:
            return None
        soup = BeautifulSoup(html, "lxml")
        return scraper.extract(soup, url)
