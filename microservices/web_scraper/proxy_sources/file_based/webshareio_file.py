from typing import Dict, List, Optional

from microservices.web_scraper.proxy_sources.base_classes import ProxyUtils
from microservices.web_scraper.proxy_sources.file_based.json_file import \
    JsonFileSource

# --- Type Hinting for Clarity ---
ProxyDict = Dict[str, List[str]]
ProxyRequestDict = Optional[Dict[str, str]]

class WebshareIOFileSource(JsonFileSource):
    """Specialized JSON source for Webshare.io proxy format."""

    def __init__(self, file_path: str):
        super().__init__(
            "Saved WebshareIO",
            file_path,
            str_manip_func=ProxyUtils.normalize_scheme_webshario,
        )
