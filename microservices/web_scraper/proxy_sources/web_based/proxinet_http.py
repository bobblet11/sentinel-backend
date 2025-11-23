from typing import Dict, List, Optional, Set

from bs4 import BeautifulSoup

from microservices.web_scraper.proxy_sources.base_classes import (
    HttpProxySource,
    normalize_proxy_scheme,
)

# --- Type Hinting for Clarity ---
ProxyDict = Dict[str, List[str]]
ProxyRequestDict = Optional[Dict[str, str]]


class ProxiNetHttpSource(HttpProxySource):
    """Scrapes HTTP/HTTPS proxies from free-proxy-list.net."""

    URL = "https://free-proxy-list.net/"

    def _parse_html_table(self, html_content: str) -> List[str]:
        """Parses the HTML table from free-proxy-list.net."""
        https_proxies: Set[str] = set()
        try:
            soup = BeautifulSoup(html_content, features="html.parser")
            tbody = soup.find("tbody")
            if not tbody:
                print(
                    f"[{self.name}] [!] Could not find tbody. Site layout may have changed."
                )
                return []

            rows = tbody.find_all("tr")
            for row in rows:
                cols = row.find_all("td")
                if len(cols) >= 7 and cols[6].text.strip().lower() == "yes":
                    ip, port = cols[0], cols[1]
                    https_proxies.add(
                        normalize_proxy_scheme(f"{ip}:{port}", scheme="http")
                    )

        except Exception as e:
            print(f"[{self.name}] [!] Error parsing HTML: {e}")

        return list(https_proxies)

    def get_proxies(
        self, bootstrap_proxies: Optional[Dict[str, str]] = None
    ) -> Dict[str, List[str]]:
        """Fetches HTTPS proxies by scraping the webpage."""

        https_proxies = self._fetch_from_url(
            self.URL, bootstrap_proxies, self._parse_html_table
        )
        return {"https": https_proxies, "socks4": [], "socks5": []}
