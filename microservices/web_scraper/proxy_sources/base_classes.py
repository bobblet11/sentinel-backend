import os
from abc import ABC, abstractmethod
from typing import Callable, Dict, List, Optional, Tuple

import requests

from microservices.web_scraper.managers.user_agent_manager import user_agent_manager

# --- Type Hinting for Clarity ---
ProxyDict = Dict[str, List[str]]
ProxyRequestDict = Optional[Dict[str, str]]


def normalize_proxy_scheme(proxy_str: str, scheme: str = "http") -> str:
    """Ensures a proxy string has a scheme, defaulting if missing."""

    if scheme == "socks5":
        scheme = "socks5h"

    if "://" not in proxy_str:
        return f"{scheme}://{proxy_str}"
    else:
        parts = proxy_str.split("://")
        return f"{scheme}://{parts[1]}"
    return proxy_str


class ProxySource(ABC):
    """
    Abstract base interface for any proxy fetching or reading mechanism.
    """

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def get_proxies(self, bootstrap_proxies: ProxyRequestDict = None) -> ProxyDict:
        """
        Abstract method to get proxies.
        Returns a dictionary categorized by proxy type ('https', 'socks4', 'socks5').
        """


class FileProxySource(ProxySource):
    """
    Abstract base interface for any proxy fetching or reading mechanism.
    """

    def __init__(
        self,
        name: str,
        file_path: str,
        str_manip_func: Optional[Callable[[str], str]] = None,
    ):
        super().__init__(name)
        self.file_path = file_path
        self.str_manip_func = str_manip_func or (lambda s: s)

    @abstractmethod
    def _parse_file_content(self, content: str) -> ProxyDict:
        """Parses raw file content into categorized proxy lists."""

    @abstractmethod
    def _format_for_save(self, proxies: ProxyDict) -> str:
        """Formats the proxies into a string for saving to a file."""

    def get_proxies(self, bootstrap_proxies: ProxyRequestDict = None) -> ProxyDict:
        """Reads and parses proxies from the file path."""

        if bootstrap_proxies:
            print(
                f"[{self.name}] File sources require no bootstrap_proxy. Ignoring it..."
            )

        if not os.path.exists(self.file_path):
            print(f"[{self.name}] [!] No file found at {self.file_path}.")
            return {"https": [], "socks4": [], "socks5": []}

        print(f"[{self.name}] Reading file {self.file_path} to get proxies...")
        try:
            with open(self.file_path, "r", encoding="utf-8") as file:
                content = file.read()
            proxies = self._parse_file_content(content)
            print(
                f"[{self.name}] [+] Proxies found:\n\tHTTPS: {len(proxies.get('https',[]))}\n\tSOCKS4: {len(proxies.get('socks4',[]))}\n\tSOCKS5: {len(proxies.get('socks5',[]))}"
            )
            return proxies

        except Exception as e:
            print(f"[{self.name}] [!] Error loading or parsing {self.file_path}: {e}")
            return {"https": [], "socks4": [], "socks5": []}

    def save_proxies(self, proxies: ProxyDict):
        """Saves categorized proxies to the file."""

        if not os.path.exists(self.file_path):
            print(f"[{self.name}] [!] No file found at {self.file_path}.")
            return

        print(f"[{self.name}] Saving proxies to {self.file_path}...")
        try:
            formatted_proxies = self._format_for_save(proxies)
            with open(self.file_path, "w", encoding="utf-8") as file:
                file.write(formatted_proxies)
            print(f"[{self.name}] [+] Proxies saved successfully")

        except Exception as e:
            print(
                f"[{self.name}] [!] Error formatting or saving proxies to {self.file_path}: {e}"
            )


class HttpProxySource(ProxySource):
    """
    Abstract base class for proxy sources that fetch proxies over HTTP/HTTPS.
    """

    def __init__(self, name: str, timeout: Tuple[float, float]):
        super().__init__(name)
        self.timeout = timeout

    def _fetch_from_url(
        self, url: str, proxies: ProxyRequestDict, parser: Callable[[str], List[str]]
    ) -> List[str]:
        """Helper to make an HTTP request and parse the response."""

        headers = {
            "User-Agent": user_agent_manager.get_random_agent(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

        try:
            response = requests.get(
                url, headers=headers, proxies=proxies, timeout=self.timeout
            )
            response.raise_for_status()
            proxies_found = parser(response.text)
            print(
                f"[{self.name}] [+] Successfully fetched {len(proxies_found)} from {url}"
            )
            return proxies_found
        except requests.exceptions.RequestException as e:
            print(f"[{self.name}] [!] Error fetching from {url}: {e}")
            return []

    @abstractmethod
    def get_proxies(self, bootstrap_proxies: ProxyRequestDict = None) -> ProxyDict:
        """Fetches and processes proxies from remote URLs."""
