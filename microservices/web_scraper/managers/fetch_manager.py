import threading

import requests

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
                    print(
                        "FetchManager instance does not exist. Creating new instance..."
                    )
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):

        if getattr(self, "_initialized", False):
            return
        with self._init_lock:
            if getattr(self, "_initialized", False):
                return

            print("Initializing FetchManager state for the first time...")
            self._initialized = True

    def fetch_article_html(url):
        """Fetches the HTML of a webpage using rotating headers and proxies."""
        try:
            headers = {"User-Agent": user_agent_manager.get_random_agent()}
            proxies = (
                proxy_rotator.get_proxy()
            )  # Assuming this returns a dict like {'http': '...', 'https': '...'}

            response = requests.get(url, headers=headers, proxies=proxies, timeout=15)
            response.raise_for_status()  # Raises an exception for bad status codes (4xx or 5xx)
            return response.text

        except requests.exceptions.RequestException as e:
            print(f"Error fetching {url}: {e}")
            return None


if __name__ == "__main__":
    fetch_manager = FetchManager()
