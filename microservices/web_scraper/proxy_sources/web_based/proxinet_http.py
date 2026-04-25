from typing import Dict, List, Optional, Set

from bs4 import BeautifulSoup

from microservices.web_scraper.proxy_sources.base_classes import (
    HttpProxySource,
    ProxyUtils,
)

# --- Type Hinting for Clarity ---
ProxyDict = Dict[str, List[str]]
ProxyRequestDict = Optional[Dict[str, str]]


class ProxiNetHttpSource(HttpProxySource):
    """Scrapes HTTP/HTTPS proxies from free-proxy-list.net."""

    URL: str = "https://free-proxy-list.net/"

    def _parse_html_table(self, html_content: str) -> List[str]:
        """Parses the HTML table from free-proxy-list.net."""

        try:
            https_proxies: Set[str] = set()
            soup = BeautifulSoup(html_content, features="html.parser")
            tbody = soup.find("tbody")

            if not tbody:
                raise Exception(f"Could not find tbody. Site layout may have changed.")

            rows = tbody.find_all("tr")

            for row in rows:
                cols = row.find_all("td")
                if len(cols) >= 7 and cols[6].text.strip().lower() == "yes":
                    ip, port = cols[0], cols[1]

                    https_proxies.add(
                        ProxyUtils.normalize_scheme(f"{ip}:{port}", scheme="http")
                    )

            return list(https_proxies)

        except Exception as e:
            self.logger.error(f"Could not parse proxinet HTML: {e}")
            return []

    def get_proxies(
        self, bootstrap_proxies: Optional[Dict[str, str]] = None
    ) -> Dict[str, List[str]]:
        """Fetches HTTPS proxies by scraping the webpage. Proxinet only provides HTTPS proxies"""
        https_proxies = self._fetch_from_url(
            self.URL, bootstrap_proxies, self._parse_html_table
        )
        return {"https": https_proxies, "socks4": [], "socks5": []}
