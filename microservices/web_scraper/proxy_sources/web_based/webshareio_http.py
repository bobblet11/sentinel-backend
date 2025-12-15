from typing import Dict, List, Optional
from microservices.web_scraper.proxy_sources.base_classes import (
    HttpProxySource,
)
from microservices.web_scraper.config import WEBSHARIO_URL

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


class WebshareIOHttpSource(HttpProxySource):
    """Specialized JSON source for Webshare.io proxy format."""
    BASE_URL = WEBSHARIO_URL
    
    def get_proxies(self, bootstrap_proxies: ProxyRequestDict = None) -> ProxyDict:
        """Fetches HTTPS, SOCKS4, and SOCKS5 proxies from Proxifly."""

        def parse_line_fun(text: str):
            lines = text.splitlines()
            return [
                normalize_proxy_scheme_webshare_io(line.strip()) for line in lines if line.strip()
            ]

        line_parser = parse_line_fun

        https = self._fetch_from_url(
            f"{self.BASE_URL}", bootstrap_proxies, line_parser
        )


        return {"https": https, "socks4": [], "socks5": []}
