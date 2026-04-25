import random
import threading
from logging import Logger, getLogger
from typing import Dict, List, Optional, Set

from common.requests.retry_request import exponential_retry
from microservices.web_scraper.proxy_sources.web_based.webshareio_http import (
    WebshareIOHttpSource,
)

# --- Type Hinting for Clarity ---
ProxyDict = Dict[str, List[str]]
ProxyDictSet = Dict[str, Set[str]]
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

    def __init__(self):

        if getattr(self, "_initialized", False):
            return

        with self._init_lock:
            if getattr(self, "_initialized", False):
                return

            self.logger: Logger = getLogger("proxy_manager_SELENIUM")
            self.logger.info("Starting initialisation")

            # --- State ---
            self.proxies: ProxyDictSet = {
                "https": set(),
                "socks4": set(),
                "socks5": set(),
            }
            self.rotate_index: int = 0
            self.fail_count: int = 0
            self.acceptable_failure_rate: float = 0.1

            # --- Concurrency ---
            self._refresh_lock = threading.Lock()

            # --- Dependency Injection for Sources ---
            self.webshareio_http_source = WebshareIOHttpSource(
                "WebshareIoHttp", timeout=(60.0, 60.0)
            )

            try:
                self._init_proxies()
            except Exception as e:
                self.logger.error(f"Failed to load proxies: {e}")
                raise

            self._initialized = True
            self.logger.info("Initialisation complete!")

    @exponential_retry(
        max_attempts=3,
        initial_delay_s=10,
        on_exceptions=(Exception),
    )
    def _init_proxies(self):
        self.proxies["https"].update(self.webshareio_http_source.get_proxies()["https"])
        self.ip_country_mapping: Dict[str, str] = (
            self.webshareio_http_source.ip_country_mapping
        )
        self.country_ip_mapping: Dict[str, str] = (
            self.webshareio_http_source.country_ip_mapping
        )

    def reset(self):
        """Testing aid: clear caches and force next call to rebuild."""
        with self._refresh_lock:
            self.proxies = {"https": set(), "socks4": set(), "socks5": set()}
            self._init_proxies()

    def get_random_proxy(self) -> ProxyRequestDict:
        """
        Public method to get a single, random, working proxy.
        """

        all_usable_proxies: Set[str] = self._get_all_usable_proxies()
        if not all_usable_proxies:
            self.logger.error("No usable proxies available!")
            return None

        chosen_global_proxy: str = random.choice(list(all_usable_proxies))
        return self._create_proxy_dict(chosen_global_proxy)

    def get_next_proxy(self, article_url: str = "") -> ProxyRequestDict:
        """
        Public method to get a proxy and rotate to next proxy.
        """
        with self._refresh_lock:
            all_usable_proxies: Set[str] = self._get_all_usable_proxies()
            if not all_usable_proxies:
                raise Exception("No usable proxies available!")

            # Should not use US proxy for BBC since they have stricter paywall
            if "bbc" in article_url:
                index: int = self.rotate_index % len(self.country_ip_mapping)
                chosen_british_proxy: str = self.country_ip_mapping["GB"][index]
                return self._create_proxy_dict(chosen_british_proxy)

            chosen_global_proxy = list(all_usable_proxies)[self.rotate_index]
            self.rotate_index = (self.rotate_index + 1) % len(all_usable_proxies)
            return self._create_proxy_dict(chosen_global_proxy)

    def report_bad_proxy(self, proxy_url: str) -> None:
        """Does not need to do anything for paid proxies"""
        self.logger.warning(f"proxy {proxy_url} failed")
        self.fail_count += 1

        if self.fail_count > self.acceptable_failure_rate * len(
            self._get_all_usable_proxies()
        ):
            self.reset()
            self.fail_count = 0
        return

    def _get_all_usable_proxies(self) -> Set[str]:
        """Returns a unified set of all valid proxies."""
        return self.proxies["https"] | self.proxies["socks4"] | self.proxies["socks5"]

    @staticmethod
    def _create_proxy_dict(proxy_url: str) -> ProxyRequestDict:
        """Creates a correctly formatted proxy dictionary for `requests`."""
        return {"http": proxy_url, "https": proxy_url}


proxy_manager_paid = ProxyManagerPaid()
