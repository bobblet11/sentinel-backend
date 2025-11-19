import datetime
import os
import random
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Set, Tuple

import requests
from microservices.web_scraper.config import PROXY_VALIDATION_MAX_WORKERS
from microservices.web_scraper.managers.proxy_class import (
    JsonFileSource,
    ProxiflyHttpSource,
    ProxiNetHttpSource,
    ProxySource,
    WebshareIOFileSource,
    normalize_proxy_scheme,
)

ONE_DAY_IN_SECONDS = 86400
DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
MIN_USABLE_PROXIES = 15

# --- Type Hinting for Clarity ---
ProxyDict = Dict[str, List[str]]
ProxyRequestDict = Optional[Dict[str, str]]


class ProxyManager:
    """
    A thread-safe Singleton class that fetches, validates, and rotates proxies
    from multiple sources. It intelligently refreshes its proxy list only when
    needed (i.e., when the list is empty or the data is stale).
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
        self,
        sources: Optional[List[ProxySource]],
        refresh_interval_seconds: int = ONE_DAY_IN_SECONDS,
        test_url: str = "https://httpbin.org/ip",
        timeout: Tuple[float, float] = (10.0, 12.0),
        max_workers: int = PROXY_VALIDATION_MAX_WORKERS,
    ):

        if getattr(self, "_initialized", False):
            return

        with self._init_lock:
            if getattr(self, "_initialized", False):
                return

            print("Initializing ProxyManager state for the first time...")

            # --- State ---
            self.proxies: ProxyDict = {"https": set(), "socks4": set(), "socks5": set()}
            self.datetime_last_fetched: Optional[datetime.datetime] = None
            self._refresh_lock = threading.Lock()
            self.rotate_index: int = 0

            # Config
            self.refresh_interval_seconds = refresh_interval_seconds
            self.test_url = test_url
            self.timeout = timeout
            self.max_workers = max_workers

            # Concurrency
            self._refresh_lock = threading.Lock()

            # --- Dependency Injection for Sources ---
            script_dir = os.path.dirname(os.path.abspath(__file__))

            self.saved_json_source = JsonFileSource(
                "Saved Proxies", os.path.join(script_dir, "saved_proxies.json")
            )
            self.saved_webshareio_source = WebshareIOFileSource(
                os.path.join(script_dir, "webshareio_proxies.json")
            )

            if sources is None:
                self.sources = [
                    ProxiNetHttpSource(timeout=self.timeout),
                    ProxiflyHttpSource(timeout=self.timeout),
                ]
            else:
                self.sources = sources

            self._load_and_validate_initial_proxies()
            self._perform_full_refresh()
            self._initialized = True
            print("[*] ProxyManager Initialisation complete!")

    def _load_and_validate_initial_proxies(self):
        """Loads proxies from the persistent cache and validates them on startup."""
        print("[*] Loading and validating saved proxies...")
        saved_proxies = self.saved_json_source.get_proxies()
        saved_webshareio_https_proxies = self.saved_webshareio_source.get_proxies()[
            "https"
        ]
        # Convert lists to sets for validation
        candidates = {
            "https": set(saved_proxies.get("https", [])),
            "socks4": set(saved_proxies.get("socks4", [])),
            "socks5": set(saved_proxies.get("socks5", [])),
        }

        candidates["https"].update(saved_webshareio_https_proxies)

        self.proxies = self._validate_proxies(candidates)
        self._log_proxy_counts("Validated saved proxies")
        return

    def refresh_now(self):
        with self._refresh_lock:
            self._perform_full_refresh()

    def reset(self):
        """Testing aid: clear caches and force next call to rebuild."""
        with self._refresh_lock:
            self.proxies = {"https": [], "socks4": [], "socks5": []}
            self.datetime_last_fetched = None

    def get_random_proxy(self) -> ProxyRequestDict:
        """
        Public method to get a single, random, working proxy.
        Triggers a refresh if the proxy pool is stale or too small.
        If run multiple times, the same result may occur
        """
        self._refresh_proxies_if_needed()

        all_usable_proxies = self._get_all_usable_proxies()
        if not all_usable_proxies:
            print("[!] CRITICAL: No usable proxies available after refresh attempt.")
            return None

        chosen_proxy = random.choice(list(all_usable_proxies))
        return self._create_proxy_dict(chosen_proxy)

    def get_next_proxy(self) -> ProxyRequestDict:
        """
        Public method to get a proxy and rotate to next proxy.
        Triggers a refresh if the proxy pool is stale or too small.
        """
        self._refresh_proxies_if_needed()

        all_usable_proxies = self._get_all_usable_proxies()
        if not all_usable_proxies:
            print("[!] CRITICAL: No usable proxies available after refresh attempt.")
            return None

        chosen_proxy = list(all_usable_proxies)[self.rotate_index]
        self.rotate_index = (self.rotate_index + 1) % len(all_usable_proxies)
        return self._create_proxy_dict(chosen_proxy)

    def _get_all_usable_proxies(self) -> Set[str]:
        """Returns a unified set of all valid proxies."""
        return self.proxies["https"] | self.proxies["socks4"] | self.proxies["socks5"]

    def _refresh_proxies_if_needed(self) -> None:
        """Checks if a refresh is needed and performs it under a lock."""

        if not self._should_refresh():
            return

        with self._refresh_lock:
            # Double-check inside the lock to prevent a race condition
            if not self._should_refresh():
                print(
                    "[*] Refresh was needed, but another thread completed it. Skipping."
                )
                return

            print("[*] Proxy list is empty or stale. Performing a full refresh...")
            self._perform_full_refresh()

    def _should_refresh(self) -> bool:
        """Determines if a refresh is required."""
        capable_proxies_count = len(self._get_all_usable_proxies())
        is_too_low = capable_proxies_count < MIN_USABLE_PROXIES
        if self.datetime_last_fetched:
            age = (datetime.datetime.now() - self.datetime_last_fetched).total_seconds()
            return is_too_low or age > self.refresh_interval_seconds
        return True

    def _perform_full_refresh(self) -> None:
        """Fetches, validates, and merges proxies from all sources."""
        print("\n--- Full Proxy Refresh ---")

        bootstrap_candidates: Set[str] = self._get_all_usable_proxies()
        newly_fetched_proxies: ProxyDict = {
            "https": set(),
            "socks4": set(),
            "socks5": set(),
        }

        for source in self.sources:
            print(f"[*] Fetching proxies from {source.name}...")
            bootstrap_proxy = (
                self._create_proxy_dict(random.choice(list(bootstrap_candidates)))
                if bootstrap_candidates
                else None
            )
            print(f"[*] Using bootstrap proxy\n{bootstrap_proxy}")
            # Fetch untested proxies from the source
            untested = source.get_proxies(bootstrap_proxy)
            for p_type in untested:
                newly_fetched_proxies[p_type].update(untested[p_type])

        print("[*] Incorporating webshare.io proxies")
        newly_fetched_proxies["https"].update(
            self.saved_webshareio_source.get_proxies()
        )

        print("[*] Validating all fetched proxies...")
        validated_new_proxies = self._validate_proxies(newly_fetched_proxies)

        for p_type in self.proxies:
            self.proxies[p_type].update(validated_new_proxies[p_type])

        self.datetime_last_fetched = datetime.datetime.now()

        self.saved_json_source.save_proxies(
            {
                "https": list(self.proxies["https"]),
                "socks4": list(self.proxies["socks4"]),
                "socks5": list(self.proxies["socks5"]),
            }
        )
        self.rotate_index = 0
        self._log_proxy_counts("Refresh complete")

    def _validate_proxies(self, candidates: ProxyDict) -> ProxyDict:
        """Tests proxies concurrently and returns a dictionary of valid ones."""
        validated: ProxyDict = {"https": set(), "socks4": set(), "socks5": set()}

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Create a list of (proxy, type) tuples
            tasks = []
            for p_type, proxy_set in candidates.items():
                tasks.extend([(proxy, p_type) for proxy in proxy_set])

            # Execute all tests
            results = executor.map(lambda p: self._test_proxy(*p), tasks)

            # Collect valid results
            for proxy, p_type in results:
                if proxy:
                    validated[p_type].add(proxy)

        return validated

    def _test_proxy(self, proxy: str, p_type: str) -> Optional[Tuple[str, str]]:
        """Tests a single proxy against the test URL."""

        schemes = {"https": "http", "socks4": "socks4", "socks5": "socks5h"}
        scheme = schemes.get(p_type)
        if not scheme:
            return None, None

        proxy_url = normalize_proxy_scheme(proxy, scheme)

        try:
            response = requests.get(
                self.test_url,
                proxies={"http": proxy_url, "https": proxy_url},
                timeout=self.timeout,
            )
            response.raise_for_status()
            return proxy_url, p_type
        except Exception:
            return None, None

    def _log_proxy_counts(self, context_message: str):
        """Helper to print the current proxy counts."""
        print(f"[*] {context_message}:")
        print(f"\tHTTPS: {len(self.proxies['https'])}")
        print(f"\tSOCKS4: {len(self.proxies['socks4'])}")
        print(f"\tSOCKS5: {len(self.proxies['socks5'])}")
        print(f"\tTotal Usable: {len(self._get_all_usable_proxies())}")

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

    @staticmethod
    def _create_proxy_dict(proxy_url: str) -> ProxyRequestDict:
        """Creates a correctly formatted proxy dictionary for `requests`."""
        return {"http": proxy_url, "https": proxy_url}


proxinet_source = ProxiNetHttpSource("ProxiNetHttpSource", timeout=(20, 22))
proxifly_source = ProxiflyHttpSource("ProxiflyHttpSource", timeout=(20, 22))
proxy_manager = ProxyManager(sources=[proxinet_source, proxifly_source])
