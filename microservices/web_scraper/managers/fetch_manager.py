import threading
from typing import Dict, Tuple

import requests
from requests.exceptions import RequestException

from common.requests.retry_request import exponential_retry
from microservices.web_scraper.managers.proxy_manager_paid import proxy_manager_paid, ProxyManagerPaid
from microservices.web_scraper.managers.proxy_manager import proxy_manager, ProxyManager
from microservices.web_scraper.managers.user_agent_manager import user_agent_manager


class FetchManager:
    """
    A thread-safe Singleton class that fetches news URLs.
    """

    _instance = None
    _class_lock = threading.Lock()  # guards instance creation
    _init_lock = threading.Lock()  # guards first-time init

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._class_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
        self,
        default_timeout: Tuple[float, float] = (15.0, 20.0),  # (connect, read)
        proxy_manager: ProxyManagerPaid | ProxyManager = proxy_manager
    ):

        if getattr(self, "_initialized", False):
            return

        with self._init_lock:
            if getattr(self, "_initialized", False):
                return

            print("[*] Initializing FetchManager state for the first time...")

            # State
            self.timeout = default_timeout
            self.proxy_manager = proxy_manager
            print("[*] FetchManager Initialisation complete!")

    def _create_enhanced_headers(self, user_agent: str) -> Dict[str, str]:
        """Returns a dictionary of headers to better mimic a real browser."""
        return {
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
        }

    @exponential_retry(
        max_attempts=5,
        initial_delay_s=1.0,
        growth_rate=0.5,
        jitter=True,
        on_exceptions=(RequestException,),
    )
    def fetch_article_html(self, url: str):
        """
        Fetches the HTML of a webpage using rotating headers and proxies.
        This method is wrapped by a retry decorator. It is responsible for
        a SINGLE fetch attempt and for reporting bad proxies.
        """
        proxies = self.proxy_manager.get_next_proxy()
        if not proxies:
            raise RequestException("No proxies available in the pool.")

        user_agent = user_agent_manager.get_random_agent()
        headers = self._create_enhanced_headers(user_agent)
        proxy_url_for_reporting = proxies.get("https", proxies.get("http"))

        try:
            response = requests.get(
                url, headers=headers, proxies=proxies, timeout=self.timeout
            )

            response.raise_for_status()

            print(f"[SUCCESS] Successfully fetched {url}")
            return response.text

        except requests.exceptions.RequestException as e:
            self.proxy_manager.report_bad_proxy(proxy_url_for_reporting)
            raise e


fetch_manager = FetchManager(proxy_manager=proxy_manager_paid)
