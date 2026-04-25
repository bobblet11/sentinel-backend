from abc import ABC, abstractmethod
from logging import getLogger
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from requests import Response, exceptions, get

from common.requests.user_agent_manager import user_agent_manager

# --- Type Hinting for Clarity ---
ProxyDict = Dict[str, List[str]]
ProxyRequestDict = Optional[Dict[str, str]]
    
class ProxyUtils:
    @staticmethod
    def normalize_scheme(proxy_str: str, scheme: str = "http") -> str:
        """Ensures a proxy string has a scheme, defaulting if missing."""

        if scheme == "socks5":
            scheme = "socks5h"

        if "://" not in proxy_str:
            return f"{scheme}://{proxy_str}"
        else:
            parts = proxy_str.split("://")
            return f"{scheme}://{parts[1]}"
    
    @staticmethod
    def normalize_scheme_webshario(proxy_str: str) -> str:
        """Normalizes Webshare.io 'ip:port:user:pass' format to 'http://user:pass@ip:port'."""
        try:
            ip, port, username, password = proxy_str.split(":")
            return f"http://{username}:{password}@{ip}:{port}"
        except ValueError:
            return ""

    @staticmethod
    def get_proxy_country(proxy_url: str, country_reflection_url:str="http://ip-api.com/json", timeout:Tuple[str,str]=(20,20), default_country:str="US")->str:
        """
        Finds the country a proxy is located in. Defaults to US if cannot be found
        
        proxy_url format: 'ip:port' or 'user:pass@ip:port'
        Returns: 2-letter country code (e.g., 'US', 'FR')
        """
        try:
            proxies:Dict[str,str] = {
                "http": proxy_url,
                "https": proxy_url,
            }
            response:Response = get(
                country_reflection_url, proxies=proxies, timeout=timeout
            )
            data:Dict[str,Any] = response.json()
            
            return (proxy_url, data.get("countryCode", default_country))
        
        except Exception:
            return (proxy_url, "US")

class ProxySource(ABC):
    """
    Abstract base interface for any proxy fetching or reading mechanism.
    """

    def __init__(self, name: str):
        self.name = name
        self.logger = getLogger(f"ProxySource.{name}")

    @abstractmethod
    def get_proxies(self, bootstrap_proxies: ProxyRequestDict = None) -> ProxyDict:
        """
        Abstract method to get proxies.
        Returns a dictionary categorized by proxy type ('https', 'socks4', 'socks5').
        """
    
    def log_summary(self, proxies: ProxyDict) -> None: 
        count_summary = ", ".join([f"{k.upper()}:{len(v)}" for k, v in proxies.items()])
        self.logger.info(count_summary)
        
class FileProxySource(ProxySource):
    """
    Abstract base interface for any proxy fetching or reading mechanism.
    """

    def __init__(
        self,
        name: str,
        file_path: Path,
    ):
        super().__init__(name)
        self.file_path: Path = file_path

    
    @abstractmethod
    def _parse_file_content(self, content: str) -> ProxyDict:
        """Parses raw file content into categorized proxy lists."""
    
    @abstractmethod
    def _format_for_save(self, proxies: ProxyDict) -> str:
        """Formats the proxies into a string for saving to a file."""
    
    def get_proxies(self, bootstrap_proxies: ProxyRequestDict = None) -> ProxyDict:
        """Reads and parses proxies from the file path."""

        if bootstrap_proxies:
            self.logger.debug(f"File sources require no bootstrap_proxy. Ignoring it...")
        
        self.logger.info(f"Reading file {self.file_path} to get proxies...")
        try:
            
            content = self.file_path.read_text(encoding="utf-8")
            proxies = self._parse_file_content(content)
            self.log_summary(proxies)
            return proxies
        
        except FileNotFoundError: 
            self.logger.error(f"No file found at {self.file_path}!")
            return {"https": [], "socks4": [], "socks5": []}
        
        except Exception as e:
            self.logger.error(f"Error loading or parsing {self.file_path}: {e}")
            return {"https": [], "socks4": [], "socks5": []}

    def save_proxies(self, proxies: ProxyDict) -> None:
        """Saves categorized proxies to the file."""
        self.logger.info(f"Saving proxies to {self.file_path}...")
        
        try:
            formatted_content = self._format_for_save(proxies)
            self.file_path.write_text(formatted_content, encoding="utf-8")
            self.logger.info(f"Proxies saved successfully")
        
        except FileNotFoundError: 
            self.logger.error(f"No file found at {self.file_path}!")
        
        except Exception as e:
            self.logger.info(
                f"Error formatting or saving proxies to {self.file_path}: {e}"
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
            "User-Agent": user_agent_manager.generate_profile().user_agent_string,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

        try:
            response: Response = get(
                url, 
                headers=headers, 
                proxies=proxies, 
                timeout=self.timeout
            )
            
            response.raise_for_status()
            
            proxies_found:List[str] = parser(response.text)
            self.logger.info(
                f"Successfully fetched {len(proxies_found)} from {url}"
            )
            return proxies_found
        
        except exceptions.Timeout:
            self.logger.warning(f"Timeout connecting to {url}")
            raise
        except exceptions.RequestException as e:
            self.logger.error(f"HTTP Error fetching {url}: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error parsing {url}: {e}")
            raise

    @abstractmethod
    def get_proxies(self, bootstrap_proxies: ProxyRequestDict = None) -> ProxyDict:
        """Fetches and processes proxies from remote URLs."""
