import random
import threading

from fake_useragent import UserAgent


class UserAgentManager:
    """
    A singleton class that contains all functions related to rotating user-agents.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        """
        before __init__, make sure no other class
        instance already exists with a connection pool. Enforces Singleton rule.
        """

        # Singleton instance already exists
        if cls._instance is not None:
            print("ProxyHandler instance already exists. Reusing instance...")
            return cls._instance

        # Singleton instance does not exist, attempt creation with lock.
        with cls._lock:
            if cls._instance is not None:
                print("ProxyHandler instance already exists. Reusing instance...")
                return cls._instance

        cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        self.available_generators = []

        try:
            all_browser_except_safari = [
                "Google",
                "Chrome",
                "Firefox",
                "Edge",
                "Opera",
                "Android",
                "Yandex Browser",
                "Samsung Internet",
                "Opera Mobile",
                "Firefox Mobile",
                "Firefox iOS",
                "Chrome Mobile",
                "Chrome Mobile iOS",
                "Edge Mobile",
                "DuckDuckGo Mobile",
                "MiuiBrowser",
                "Whale",
                "Twitter",
                "Facebook",
                "Amazon Silk",
            ]
            ua_chrome = UserAgent(browsers=all_browser_except_safari, min_version=115.0)
            self.available_generators.append(ua_chrome)
            print("[+] Initialized modern non-safari UserAgents.")
        except Exception as e:
            print(f"[!] Could not initialize non-safari UserAgents: {e}")

        try:
            safari_browsers = ["Safari", "Mobile Safari UI/WKWebView", "Mobile Safari"]
            ua_safari = UserAgent(browsers=safari_browsers, min_version=17.0)
            self.available_generators.append(ua_safari)
            print("[+] Initialized modern Safari UserAgent.")
        except Exception as e:
            print(f"[!] Could not initialize Safari UserAgent: {e}")

    def get_random_agent(self):
        """
        Returns a random user agent from the available modern generators.
        Prioritizes Chrome, then Safari, with a final fallback.
        """

        if self.available_generators:
            # Randomly choose one of the successful generators
            chosen_generator = random.choice(self.available_generators)
            return chosen_generator.random
        else:
            # Fallback if both initializers failed
            print("[!] Both UserAgent initializers failed. Using a hardcoded fallback.")
            return "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


user_agent_manager = UserAgentManager()
