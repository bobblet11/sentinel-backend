from typing import Dict, List, Optional

from microservices.web_scraper.proxy_sources.file_based.json_file import JsonFileSource

# --- Type Hinting for Clarity ---
ProxyDict = Dict[str, List[str]]
ProxyRequestDict = Optional[Dict[str, str]]


def normalize_proxy_scheme_webshare_io(proxy_str: str) -> str:
    """Normalizes Webshare.io 'ip:port:user:pass' format to 'http://user:pass@ip:port'."""
    try:
        ip, port, username, password = proxy_str.split(":")
        return f"http://{username}:{password}@{ip}:{port}"
    except ValueError:
        print(f"Warning: Malformed webshare io proxy string: {proxy_str}. Skipping.")
        return ""


class WebshareIOFileSource(JsonFileSource):
    """Specialized JSON source for Webshare.io proxy format."""

    def __init__(self, file_path: str):
        super().__init__(
            "Saved WebshareIO",
            file_path,
            str_manip_func=normalize_proxy_scheme_webshare_io,
        )
