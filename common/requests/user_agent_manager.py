import threading
import hashlib

from typing import List, Set
from fake_useragent import UserAgent
from logging import Logger, getLogger


ALL_NON_SAFARI_BROWSERS:List[str] = [
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
ALL_SAFARI_BROWSERS:List[str] = [["Safari", "Mobile Safari UI/WKWebView", "Mobile Safari"]]
JUST_CHROME:List[str] = ["Chrome"] 
MAX_UA_POOL_SIZE:int = 150
MAX_UA_POOL_ATTEMPTS:int = 3000

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
        if getattr(self, "_initialized", False):
            return
        self.logger:Logger = getLogger("user_agent_manager")
        self.logger.info("Initialising UserAgentManager...")
        
        try:
            self.ua_engine = UserAgent(browsers=JUST_CHROME, min_version=120.0)
        except Exception as e:
            self.logger.error(f"Failed to load UserAgent source: {e}")
            self.ua_engine = None
            
        self.agent_pool: List[str] = self._generate_agent_pool()
        
        self.logger.info(f"Initialization complete! Pool size: {len(self.agent_pool)}")

    def _generate_chrome_agent_generator(self) -> UserAgent:
        """DEPRECATED"""
        try:
            self.logger.info("Generating non-safari user agents")
            chrome_user_agent_generator = UserAgent(browsers=JUST_CHROME, min_version=115.0)
            return chrome_user_agent_generator
        except Exception as e:
            self.logger.error("Could not initialize non-safari UserAgents: {e}")
            
    def _generate_safari_agent_generator(self) -> UserAgent:
        """DEPRECATED"""
        try:
            self.logger.info("Generating safari user agents")
            safari_user_agent_generator = UserAgent(browsers=ALL_SAFARI_BROWSERS, min_version=17.0)
            return safari_user_agent_generator
        except Exception as e:
            self.logger.error("Could not initialize safari UserAgents: {e}")
          
    def _generate_agent_pool(self) -> List[str]:
        """
        Generates a list of valid Chrome User Agents to use for Sticky sessions.
        """

        fallbacks:List[str] = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ]
                
        if not self.ua_engine:
            return fallbacks
    
        pool:Set[str] = set()
        attempts:int = 0
        
        try:

            while len(pool) < MAX_UA_POOL_SIZE and attempts < MAX_UA_POOL_ATTEMPTS:
                ua_string:str = self.ua_engine.random
                if ua_string:
                    pool.add(ua_string)
                attempts += 1
            
            if len(pool) < MAX_UA_POOL_SIZE:
                self.logger.warning(f"User agent pool size ({len(pool)}) is smaller than the {MAX_UA_POOL_SIZE} agent string size. Suggest reducing MAX_UA_POOL_ATTEMPTS or increasing MAX_UA_POOL_ATTEMPTS")
    
            return list(pool)
        
        except Exception as e:
            self.logger.error(f"Error generating pool: {e}")
            return fallbacks
                 
    def get_random_agent(self) -> str:
        """
        Returns a random user agent from the ua engine.
        """

        if not self.ua_engine:
            self.logger.error("UserAgent engine not initialised. Using a hardcoded fallback.")
            return "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
  
        return self.ua_engine.random

    def get_sticky_agent(self, proxy_url:str) -> str:
        """
        Returns a user agent based on the proxy url, ensuring the same user agent is used for proxy url every time.
        """

        if not self.agent_pool:
            raise Exception("User pool is not intialized!")

        if not proxy_url:
            return self.agent_pool[0]
        
        hash_val = hashlib.sha256(proxy_url.encode('utf-8')).hexdigest()
        hash_int = int(hash_val, 16)
        index = hash_int % len(self.agent_pool)
        return self.agent_pool[index]

user_agent_manager = UserAgentManager()
