# nyt_scraper.py
import re
from typing import Dict, Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from microservices.web_scraper.parsers.base_parser import BaseParser

# New York Times


class CBSParser(BaseParser):
    def extract(self, soup: BeautifulSoup, article_url: str) -> Optional[Dict]:
        return

        return {
            "title": title,
            "text": text,
            "author": author,
            "published_at": published_at,
        }
