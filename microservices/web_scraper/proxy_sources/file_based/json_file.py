import json
from typing import Dict, List, Optional

from microservices.web_scraper.proxy_sources.base_classes import FileProxySource

# --- Type Hinting for Clarity ---
ProxyDict = Dict[str, List[str]]
ProxyRequestDict = Optional[Dict[str, str]]


class JsonFileSource(FileProxySource):
    """Loads proxies from a json file."""

    def _parse_file_content(self, content: str) -> ProxyDict:
        """Parse JSON file content"""

        proxies_data: ProxyDict = json.loads(content)
        parsed_proxies: ProxyDict = {"https": [], "socks4": [], "socks5": []}

        for p_type in parsed_proxies.keys():
            for proxy_str in proxies_data.get(p_type, []):
                if transformed := self.str_manip_func(proxy_str):
                    parsed_proxies[p_type].append(transformed)
        return parsed_proxies

    def _format_for_save(self, proxies: ProxyDict) -> str:
        """Format JSON file content"""
        return json.dumps(proxies, indent=4)
