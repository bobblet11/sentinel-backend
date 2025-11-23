from typing import Dict, List, Optional

from microservices.web_scraper.proxy_sources.base_classes import (
    HttpProxySource,
    normalize_proxy_scheme,
)

# --- Type Hinting for Clarity ---
ProxyDict = Dict[str, List[str]]
ProxyRequestDict = Optional[Dict[str, str]]


class ProxiflyHttpSource(HttpProxySource):
    """Fetches proxies from the Proxifly CDN."""

    BASE_URL = (
        "https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/protocols"
    )

    def get_proxies(self, bootstrap_proxies: ProxyRequestDict = None) -> ProxyDict:
        """Fetches HTTPS, SOCKS4, and SOCKS5 proxies from Proxifly."""

        def parse_line_fun(text: str):
            lines = text.splitlines()
            return [
                normalize_proxy_scheme(line.strip()) for line in lines if line.strip()
            ]

        line_parser = parse_line_fun

        https = self._fetch_from_url(
            f"{self.BASE_URL}/https/data.txt", bootstrap_proxies, line_parser
        )
        socks4 = self._fetch_from_url(
            f"{self.BASE_URL}/socks4/data.txt", bootstrap_proxies, line_parser
        )
        socks5 = self._fetch_from_url(
            f"{self.BASE_URL}/socks5/data.txt", bootstrap_proxies, line_parser
        )
        return {"https": https, "socks4": socks4, "socks5": socks5}
