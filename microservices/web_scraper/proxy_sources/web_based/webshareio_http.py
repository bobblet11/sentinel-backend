import concurrent.futures
from typing import Callable, Dict, List, Optional

from microservices.web_scraper.config import WEBSHARIO_URL
from microservices.web_scraper.proxy_sources.base_classes import (
    HttpProxySource,
    ProxyUtils,
)

# --- Type Hinting for Clarity ---
ProxyDict = Dict[str, List[str]]
ProxyRequestDict = Optional[Dict[str, str]]


class WebshareIOHttpSource(HttpProxySource):
    """Specialized JSON source for Webshare.io proxy format."""

    URL: str = WEBSHARIO_URL

    def __init__(self, name, timeout) -> None:
        super().__init__(name, timeout)
        self.ip_country_mapping: Dict[str, str] = {}
        self.country_ip_mapping: Dict[str, str] = {}

    def get_proxies(self, bootstrap_proxies: ProxyRequestDict = None) -> ProxyDict:
        """Fetches the HTTPS proxies from webshario service"""

        def parse_line_fun(text: str) -> List[str]:
            lines: List[str] = text.splitlines()
            return [
                ProxyUtils.normalize_scheme_webshario(line.strip())
                for line in lines
                if line.strip()
            ]

        line_parser: Callable[[str], List[str]] = parse_line_fun

        self.logger.info("Fetching proxies from Webshare.io")
        https: List[str] = self._fetch_from_url(
            f"{self.URL}", bootstrap_proxies, line_parser
        )
        self.logger.info(f"Found https {https}")
        self.logger.info("Attempting to create country map (default = US)")
        self.update_mappings(https)

        return {"https": https or [], "socks4": [], "socks5": []}

    def update_mappings(self, proxies: List[str]) -> None:
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:

            if proxies is None:
                self.logger.warning("No proxies returned from Webshare")
                return {}
            future_proxy_countries = executor.map(ProxyUtils.get_proxy_country, proxies)
            ip_country_mapping: Dict[str, str] = {}
            country_ip_mapping: Dict[str, str] = {}

            for proxy_str, country in future_proxy_countries:
                ip_country_mapping[proxy_str] = country

                if not country_ip_mapping.get(country, None):
                    country_ip_mapping[country] = [proxy_str]
                else:
                    country_ip_mapping[country].append(proxy_str)

        self.ip_country_mapping = ip_country_mapping
        self.country_ip_mapping = country_ip_mapping
