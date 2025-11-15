import json
import os
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Set, Tuple, Callable

import requests
from bs4 import BeautifulSoup

from microservices.web_scraper.managers.user_agent_manager import user_agent_manager

# --- Type Hinting for Clarity ---
ProxyDict = Dict[str, List[str]]
ProxyRequestDict = Optional[Dict[str, str]]


def normalize_proxy_scheme(proxy_str: str, scheme: str = "http") -> str:
    """Ensures a proxy string has a scheme, defaulting if missing."""
    if "://" not in proxy_str:
        return f"{scheme}://{proxy_str}"
    return proxy_str

def normalize_proxy_scheme_webshare_io(proxy_str: str) -> str:
    """Normalizes Webshare.io 'ip:port:user:pass' format to 'http://user:pass@ip:port'."""
    try:
        ip, port, username, password = proxy_str.split(':')
        return f"http://{username}:{password}@{ip}:{port}"
    except ValueError:
        print(f"Warning: Malformed webshare io proxy string: {proxy_str}. Skipping.")
        return ""


# --- Interfaces and Base Classes for Proxy Sources ---

class ProxySource(ABC):
    """
    Abstract base interface for any proxy fetching or reading mechanism.
    """
    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def get_proxies(self, bootstrap_proxies: ProxyRequestDict  = None) -> ProxyDict:
        """
        Abstract method to get proxies.
        Returns a dictionary categorized by proxy type ('https', 'socks4', 'socks5').
        """
        pass
    
    
class FileProxySource(ProxySource):
    """
    Abstract base interface for any proxy fetching or reading mechanism.
    """
    
    def __init__(self, name: str, file_path: str, str_manip_func: Optional[Callable[[str], str]] = None):
        super().__init__(name)
        self.file_path = file_path
        self.str_manip_func = str_manip_func or (lambda s: s)
    
    @abstractmethod
    def _parse_file_content(self, content: str) -> ProxyDict:
        """Parses raw file content into categorized proxy lists."""
        pass
    
    @abstractmethod
    def _format_for_save(self, proxies: ProxyDict) -> str:
        """Formats the proxies into a string for saving to a file."""
        pass
    

    def get_proxies(self, bootstrap_proxies: ProxyRequestDict = None) -> ProxyDict:
        """Reads and parses proxies from the file path."""
        
        if bootstrap_proxies:
            print(f"[{self.name}] File sources require no bootstrap_proxy. Ignoring it...")
            
        if not os.path.exists(self.file_path):
            print(f"[{self.name}] [!] No file found at {self.file_path}.")
            return {"https": [], "socks4": [], "socks5": []}
        
        print(f"[{self.name}] Reading file {self.file_path} to get proxies...")
        try:
            with open(self.file_path, "r", encoding='utf-8') as file:
                content = file.read()
            proxies = self._parse_file_content(content)
            print(f"[{self.name}] [+] Proxies found:\n\tHTTPS: {len(proxies.get('https',[]))}\n\tSOCKS4: {len(proxies.get('socks4',[]))}\n\tSOCKS5: {len(proxies.get('socks5',[]))}")
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
            with open(self.file_path, "w", encoding='utf-8') as file:
                file.write(formatted_proxies)
            print(f"[{self.name}] [+] Proxies saved successfully")
            
        except Exception as e:
            print(f"[{self.name}] [!] Error formatting or saving proxies to {self.file_path}: {e}")
    
class HttpProxySource(ProxySource):
    """
    Abstract base class for proxy sources that fetch proxies over HTTP/HTTPS.
    """
    
    def __init__(self, name: str, timeout: Tuple[float, float]):
        super().__init__(name)
        self.timeout = timeout

    def _fetch_from_url(self, url: str, proxies: ProxyRequestDict, parser: Callable[[str], List[str]]) -> List[str]:
        """Helper to make an HTTP request and parse the response."""
    
        headers = {
            "User-Agent": user_agent_manager.get_random_agent(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        
        try:
            response = requests.get(url, headers=headers, proxies=proxies, timeout=self.timeout)
            response.raise_for_status()
            proxies_found = parser(response.text)
            print(f"[{self.name}] [+] Successfully fetched {len(proxies_found)} from {url}")
            return proxies_found
        except requests.exceptions.RequestException as e:
            print(f"[{self.name}] [!] Error fetching from {url}: {e}")
            return []
    
    @abstractmethod
    def get_proxies(self, bootstrap_proxies: ProxyRequestDict = None) -> ProxyDict:
        """Fetches and processes proxies from remote URLs."""
        pass
    
    
# --- Concrete Proxy Source Implementations ---

class TextFileSource(FileProxySource):
    """Loads proxies from a txt file file."""
    
    def _parse_file_content(self, content: str) -> ProxyDict:
        """Parse TXT file content"""
        
        parsed_proxies: ProxyDict = {"https": [], "socks4": [], "socks5": []}
        
        sections = content.split('\n\n')
        # Assuming order: HTTPS, SOCKS4, SOCKS5
        if len(sections) > 0:
            parsed_proxies["https"] = [self.str_manip_func(line.strip()) for line in sections[0].splitlines() if line.strip()]
        if len(sections) > 1:
            parsed_proxies["socks4"]  = [self.str_manip_func(line.strip()) for line in sections[1].splitlines() if line.strip()]
        if len(sections) > 2:
            parsed_proxies["socks5"] = [self.str_manip_func(line.strip()) for line in sections[2].splitlines() if line.strip()]
            
        return parsed_proxies
    
    def _format_for_save(self, proxies: ProxyDict) -> str:
        """Format TXT file content"""
        https_proxies = proxies.get("https", [])
        socks4_proxies = proxies.get("socks4", [])
        socks5_proxies = proxies.get("socks5", [])
        
        https_section, socks4_section, socks5_section = "\n".join(https_proxies), "\n".join(socks4_proxies), "\n".join(socks5_proxies)
        return https_section + "\n" + socks4_section + "\n" + socks5_section

class JsonFileSource(FileProxySource):
    """Loads proxies from a json file."""
    
    def _parse_file_content(self, content: str) -> ProxyDict:
        """Parse JSON file content"""
        
        proxies_data:ProxyDict = json.loads(content)
        parsed_proxies: ProxyDict = {"https": [], "socks4": [], "socks5": []}
        
        for p_type in parsed_proxies.keys():
            for proxy_str in proxies_data.get(p_type, []):
                if transformed := self.str_manip_func(proxy_str):
                    parsed_proxies[p_type].append(transformed)
        return parsed_proxies
    
    def _format_for_save(self, proxies: ProxyDict) -> str:
        """Format JSON file content"""
        return json.dumps(proxies, indent=4)
        

class WebshareIOFileSource(JsonFileSource):
    """Specialized JSON source for Webshare.io proxy format."""
    def __init__(self, file_path: str):
        super().__init__("Saved WebshareIO", file_path, str_manip_func=normalize_proxy_scheme_webshare_io)
        
class ProxiflyHttpSource(HttpProxySource):
    """Fetches proxies from the Proxifly CDN."""
    BASE_URL = "https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/protocols"
    
    def get_proxies(self, bootstrap_proxies: ProxyRequestDict = None) -> ProxyDict:
        """Fetches HTTPS, SOCKS4, and SOCKS5 proxies from Proxifly."""
        line_parser = lambda text: [normalize_proxy_scheme(line.strip()) for line in text.splitlines() if line.strip()]
        https = self._fetch_from_url(f"{self.BASE_URL}/https/data.txt", bootstrap_proxies, line_parser)
        socks4 = self._fetch_from_url(f"{self.BASE_URL}/socks4/data.txt", bootstrap_proxies, line_parser)
        socks5 = self._fetch_from_url(f"{self.BASE_URL}/socks5/data.txt", bootstrap_proxies, line_parser)
        return {"https": https, "socks4": socks4, "socks5": socks5}

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
                print(f"[{self.name}] [!] Could not find tbody. Site layout may have changed.")
                return []

            rows = tbody.find_all("tr")
            for row in rows:
                cols = row.find_all("td")
                if len(cols) >= 7 and cols[6].text.strip().lower() == "yes":
                    ip, port = cols[0], cols[1]
                    https_proxies.add(normalize_proxy_scheme(f"{ip}:{port}", scheme = "http"))
                        
        except Exception as e:
            print(f"[{self.name}] [!] Error parsing HTML: {e}")
            
        return list(https_proxies)


    def get_proxies(self, bootstrap_proxies: Optional[Dict[str, str]] = None) -> Dict[str, List[str]]:
        """Fetches HTTPS proxies by scraping the webpage."""

        https_proxies = self._fetch_from_url(self.URL, bootstrap_proxies, self._parse_html_table)
        return {"https": https_proxies, "socks4": [], "socks5": []}
