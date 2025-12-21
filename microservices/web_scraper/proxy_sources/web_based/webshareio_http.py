from typing import Dict, List, Optional
from microservices.web_scraper.proxy_sources.base_classes import (
    HttpProxySource,
)
from microservices.web_scraper.config import WEBSHARIO_URL, PROXY_VALIDATION_MAX_WORKERS
import requests
import concurrent.futures

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
    
    def __init__(self, name, timeout):
        self.ip_country_mapping = {} # default to None for all other classes?
        super().__init__(name, timeout)
    
    def get_proxies(self, bootstrap_proxies: ProxyRequestDict = None) -> ProxyDict:
        """Fetches HTTPS, SOCKS4, and SOCKS5 proxies from Proxifly."""

        def parse_line_fun(text: str):
            lines = text.splitlines()
            return [
                normalize_proxy_scheme_webshare_io(line.strip()) for line in lines if line.strip()
            ]

        line_parser = parse_line_fun

        print(f"[{self.name}] [+] Fetching proxies from Webshare.io")
        https = self._fetch_from_url(
            f"{self.BASE_URL}", bootstrap_proxies, line_parser
        )
        
        print(f"[{self.name}] [+] Attempting to create country map (default = US)")
        self.ip_country_mapping = self.create_ip_country_mapping(https)
        return {"https": https, "socks4": [], "socks5": []}
    
    def create_ip_country_mapping(self, proxies) -> Dict[str,str]:
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=PROXY_VALIDATION_MAX_WORKERS) as executor:
            future_proxy_countries = executor.map(self.get_proxy_country, proxies)
            ip_country_mapping = {}
            for proxy_str, country in future_proxy_countries:
                ip_country_mapping[proxy_str] = country
        return ip_country_mapping
    
    def get_proxy_country(self, proxy_str):
        """
        Input format: 'ip:port' or 'user:pass@ip:port'
        Returns: 2-letter country code (e.g., 'US', 'FR')
        """
        proxies = {
            "http": proxy_str,
            "https": proxy_str,
        }
        
        try:
            # We use ip-api.com (Free, no key needed for small lists)
            response = requests.get("http://ip-api.com/json", proxies=proxies, timeout=20)
            data = response.json()
            return (proxy_str, data.get("countryCode", "US")) # Default to US if fails
        except Exception as e:
            print(f"Error checking country for {proxy_str}: {e}, defaulting to US")
            return (proxy_str, "US")
