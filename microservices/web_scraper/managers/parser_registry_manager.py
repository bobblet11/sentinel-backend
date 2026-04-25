import threading
from logging import Logger, getLogger
from typing import Dict, Optional

from microservices.web_scraper.parsers.ABC_parser import ABCParser
from microservices.web_scraper.parsers.base_parser import BaseParser
from microservices.web_scraper.parsers.BBC_parser import BBCParser
from microservices.web_scraper.parsers.CBC_parser import CBCParser
from microservices.web_scraper.parsers.CBS_parser import CBSParser
from microservices.web_scraper.parsers.Euronews_parser import EuronewsParser
from microservices.web_scraper.parsers.NBC_parser import NBCParser
from microservices.web_scraper.parsers.NPR_parser import NPRParser
from microservices.web_scraper.parsers.The_Guardian_parser import TheGuardianParser

URL_TO_PARSER_MAP: Dict[str, BaseParser] = {
    ("abcnews", "abcnews.go.com"): ABCParser(),
    ("bbc", "www.bbc.com"): BBCParser(),
    ("cbc", "www.cbc.ca"): CBCParser(),
    ("cbs", "www.cbsnews.com"): CBSParser(),
    ("euronews", "www.euronews.com"): EuronewsParser(),
    ("nbcnews", "www.nbcnews.com"): NBCParser(),
    ("npr", "www.npr.org"): NPRParser(),
    ("theguardian", "www.theguardian.com"): TheGuardianParser(),
}


class ParserRegistryManager:
    """
    Maps urls to their hardcoded parser if they exist.

    Singleton
    """

    _instance = None
    _class_lock = threading.Lock()
    _init_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._class_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:

        if getattr(self, "_initialized", False):
            return

        with self._init_lock:
            if getattr(self, "_initialized", False):
                return

            self.logger: Logger = getLogger("parser_registry_manager")
            self.logger.info("Starting initialisation")

            self.url_to_parser_map: Dict[str, BaseParser] = URL_TO_PARSER_MAP

            self._initialized = True
            self.logger.info("Initialisation complete!")

    def _match_hardcoded_parser(self, article_url: str) -> Optional[BaseParser]:
        for url_patterns, parser in self.url_to_parser_map.items():
            for pattern in url_patterns:
                if pattern in article_url:
                    return parser
        return None

    def find_matching_parser(self, article_url: str) -> Optional[BaseParser]:
        # hardcoded parsers are not setup yet, so return None for now.
        hardcoded_parser: Optional[BaseParser] = self._match_hardcoded_parser(
            article_url
        )

        if not hardcoded_parser:
            return None

        self.logger.debug(f"Using parser: {hardcoded_parser.__class__.__name__}")
        return hardcoded_parser
