import os
import random
import threading
from typing import Dict, List, Optional, Set
from microservices.web_scraper.proxy_sources.file_based.webshareio_file import (
    WebshareIOFileSource,
)
from microservices.web_scraper.proxy_sources.web_based.webshareio_http import (
    WebshareIOHttpSource,
)

# --- Type Hinting for Clarity ---
ProxyDict = Dict[str, List[str]]
ProxyRequestDict = Optional[Dict[str, str]]

class ProxyManagerPaid:
    """
    A thread-safe Singleton class that uses paid for proxies only. 
    """

    _instance = None
    _class_lock = threading.Lock()
    _init_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._class_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
        self
    ):

        if getattr(self, "_initialized", False):
            return

        with self._init_lock:
            if getattr(self, "_initialized", False):
                return
            self.name = type(self).__name__
            print(f"Initializing [{self.name}] state for the first time...")

            # --- State ---
            self.proxies = {"https": set(), "socks4": set(), "socks5": set()}
            self._refresh_lock = threading.Lock()
            self.rotate_index: int = 0

            # Concurrency
            self._refresh_lock: threading.Lock = threading.Lock()

            # --- Dependency Injection for Sources ---
            self.paid_webshareio_source: WebshareIOHttpSource = WebshareIOHttpSource("WebshareIoHttp", timeout=(20.0, 22.0))
            webshareio_https_proxies: ProxyDict = self.paid_webshareio_source.get_proxies()["https"]
            self.ip_country_mapping: Dict[str,str] = self.paid_webshareio_source.ip_country_mapping
            self.country_ip_mapping: Dict[str,str] = self.reverse_dict(self.ip_country_mapping)
            self.proxies["https"].update(webshareio_https_proxies)
            self._initialized = True
            print(f"[*] {self.name} Initialisation complete!")

    @staticmethod
    def reverse_dict(dictionary_to_reverse):
        reversed_dict = {}
        for key, value in dictionary_to_reverse.items():
            if value in reversed_dict:
                reversed_dict[value].append(key)
            else:
                reversed_dict[value] = [key]
        return reversed_dict
    
    def reset(self):
        """Testing aid: clear caches and force next call to rebuild."""
        with self._refresh_lock:
            self.proxies = {"https": [], "socks4": [], "socks5": []}

    def get_random_proxy(self) -> ProxyRequestDict:
        """
        Public method to get a single, random, working proxy.
        Triggers a refresh if the proxy pool is stale or too small.
        If run multiple times, the same result may occur
        """
        all_usable_proxies = self._get_all_usable_proxies()
        if not all_usable_proxies:
            print("[!] CRITICAL: No usable proxies available after refresh attempt.")
            return None

        chosen_proxy: str = random.choice(list(all_usable_proxies))
        return self._create_proxy_dict(chosen_proxy)

    def get_next_proxy(self, url="") -> ProxyRequestDict:
        """
        Public method to get a proxy and rotate to next proxy.
        Triggers a refresh if the proxy pool is stale or too small.
        """
        all_usable_proxies = self._get_all_usable_proxies()
        if not all_usable_proxies:
            print("[!] CRITICAL: No usable proxies available after refresh attempt.")
            return None

        if "bbc" in url:
            # shouldnt use US proxy since they have stricter paywall
            index = self.rotate_index % len(self.country_ip_mapping)
            chosen_proxy = self.country_ip_mapping["GB"][index]
            return self._create_proxy_dict(chosen_proxy)
        
        chosen_proxy = list(all_usable_proxies)[self.rotate_index]
        self.rotate_index = (self.rotate_index + 1) % len(all_usable_proxies)
        return self._create_proxy_dict(chosen_proxy)

    
    def report_bad_proxy(self, proxy_url: str) -> None:
        """Does not need to do anything for paid proxies"""
        return
    
    def _get_all_usable_proxies(self) -> Set[str]:
        """Returns a unified set of all valid proxies."""
        return self.proxies["https"] | self.proxies["socks4"] | self.proxies["socks5"]

    @staticmethod
    def _create_proxy_dict(proxy_url: str) -> ProxyRequestDict:
        """Creates a correctly formatted proxy dictionary for `requests`."""
        return {"http": proxy_url, "https": proxy_url}

proxy_manager_paid = ProxyManagerPaid()
