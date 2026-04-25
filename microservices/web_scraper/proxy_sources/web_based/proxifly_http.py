from typing import Callable, Dict, List, Optional

from microservices.web_scraper.proxy_sources.base_classes import (
    HttpProxySource,
    ProxyUtils,
)

# --- Type Hinting for Clarity ---
ProxyDict = Dict[str, List[str]]
ProxyRequestDict = Optional[Dict[str, str]]


class ProxiflyHttpSource(HttpProxySource):
    """Fetches proxies from the Proxifly CDN."""

    BASE_URL: str = (
        "https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/protocols"
    )

    def get_proxies(self, bootstrap_proxies: ProxyRequestDict = None) -> ProxyDict:
        """Fetches HTTPS, and SOCKS5 proxies from Proxifly. Proxifly has no SOCKS4"""

        def parse_line_fun(content: str) -> List[str]:
            lines: List[str] = content.splitlines()
            return [
                ProxyUtils.normalize_scheme(line.strip())
                for line in lines
                if line.strip()
            ]

        line_parser: Callable[[str], List[str]] = parse_line_fun

        https: List[str] = self._fetch_from_url(
            f"{self.BASE_URL}/https/data.txt", bootstrap_proxies, line_parser
        )

        socks5: List[str] = self._fetch_from_url(
            f"{self.BASE_URL}/socks5/data.txt", bootstrap_proxies, line_parser
        )

        return {"https": https, "socks4": [], "socks5": socks5}
