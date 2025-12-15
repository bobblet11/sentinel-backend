import os
import random
import threading
from typing import Dict, List, Optional, Set
from microservices.web_scraper.proxy_sources.file_based.webshareio_file import (
    WebshareIOFileSource,
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
            self.proxies: ProxyDict = {"https": set(), "socks4": set(), "socks5": set()}
            self._refresh_lock = threading.Lock()
            self.rotate_index: int = 0

            # Concurrency
            self._refresh_lock: threading.Lock = threading.Lock()

            # --- Dependency Injection for Sources ---
            script_dir: str = os.path.dirname(os.path.abspath(__file__))
            file_sources_dir: str = os.path.join(script_dir, "..", "proxy_sources")
            
            self.saved_webshareio_source: WebshareIOFileSource = WebshareIOFileSource(
                os.path.join(file_sources_dir, "webshareio_proxies.json")
            )
            
            self.proxies: ProxyDict = self.saved_webshareio_source.get_proxies()
            
            self._initialized = True
            print(f"[*] {self.name} Initialisation complete!")

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

    def get_next_proxy(self) -> ProxyRequestDict:
        """
        Public method to get a proxy and rotate to next proxy.
        Triggers a refresh if the proxy pool is stale or too small.
        """
        all_usable_proxies = self._get_all_usable_proxies()
        if not all_usable_proxies:
            print("[!] CRITICAL: No usable proxies available after refresh attempt.")
            return None

        chosen_proxy = list(all_usable_proxies)[self.rotate_index]
        self.rotate_index = (self.rotate_index + 1) % len(all_usable_proxies)
        return self._create_proxy_dict(chosen_proxy)
    
    def report_bad_proxy(self, proxy_url: str) -> None:
        """Removes a failing proxy from all active sets."""
        if not proxy_url:
            return

        with self._refresh_lock:
            self.proxies["https"].discard(proxy_url)
            self.proxies["socks4"].discard(proxy_url)
            self.proxies["socks5"].discard(proxy_url)
            print(
                f"[*] Reported bad proxy: {proxy_url}. Removed from active pool. Remaining: {len(self._get_all_usable_proxies())}"
            )

        self._refresh_proxies_if_needed()
    def _get_all_usable_proxies(self) -> Set[str]:
        """Returns a unified set of all valid proxies."""
        return self.proxies["https"] | self.proxies["socks4"] | self.proxies["socks5"]

    @staticmethod
    def _create_proxy_dict(proxy_url: str) -> ProxyRequestDict:
        """Creates a correctly formatted proxy dictionary for `requests`."""
        return {"http": proxy_url, "https": proxy_url}

proxy_manager_paid = ProxyManagerPaid()
