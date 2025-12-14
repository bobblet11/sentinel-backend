from typing import List, Optional

from microservices.web_scraper.parsers.base_parser import BaseParser
from microservices.web_scraper.parsers.NYT_parser import NytParser
from microservices.web_scraper.parsers.WP_parser import WpParser
from microservices.web_scraper.parsers.WSJ_parser import WsjParser


class ParserRegistryManager:
    """
    Maps urls to their hardcoded parser if they exist.
    """

    def __init__(self):
        self.hardcoded_parsers: List[BaseParser] = [
            NytParser(),
            WpParser(),
            WsjParser(),
        ]
        self.name = "ParserRegistry"

    def find_matching_parser(self, url: str) -> Optional[BaseParser]:
        for hardcoded_parser in self.hardcoded_parsers:
            try:
                if not hardcoded_parser.matches(url):
                    continue

                print(
                    f"[{self.name}] Using Parser: {hardcoded_parser.__class__.__name__}"
                )
                return hardcoded_parser

            except Exception:
                continue
        return None
