from typing import Dict, List, Optional

from microservices.web_scraper.proxy_sources.base_classes import \
    FileProxySource

# --- Type Hinting for Clarity ---
ProxyDict = Dict[str, List[str]]
ProxyRequestDict = Optional[Dict[str, str]]


class TextFileSource(FileProxySource):
    """Loads proxies from a txt file file."""
    
    def __init__(self, name, file_path, str_manip_func):
        super().__init__(name, file_path)
        self.str_manip_func = str_manip_func
        
        
    def _parse_file_content(self, content: str) -> ProxyDict:
        """Parse TXT file content assuming order: HTTPS, SOCKS4, SOCKS5"""
        
        parsed_proxies: ProxyDict = {"https": [], "socks4": [], "socks5": []}
        sections:List[str] = content.split("\n\n")
        
        
        if len(sections) > 0:
            parsed_proxies["https"] = [
                self.str_manip_func(line.strip())
                for line in sections[0].splitlines()
                if line.strip()
            ]
        if len(sections) > 1:
            parsed_proxies["socks4"] = [
                self.str_manip_func(line.strip())
                for line in sections[1].splitlines()
                if line.strip()
            ]
        if len(sections) > 2:
            parsed_proxies["socks5"] = [
                self.str_manip_func(line.strip())
                for line in sections[2].splitlines()
                if line.strip()
            ]

        return parsed_proxies

    def _format_for_save(self, proxies: ProxyDict) -> str:
        """Format TXT file content"""
        https_proxies: List[str] = proxies.get("https", [])
        socks4_proxies: List[str] = proxies.get("socks4", [])
        socks5_proxies: List[str] = proxies.get("socks5", [])

        https_section, socks4_section, socks5_section = (
            "\n".join(https_proxies),
            "\n".join(socks4_proxies),
            "\n".join(socks5_proxies),
        )
        return https_section + "\n" + socks4_section + "\n" + socks5_section
