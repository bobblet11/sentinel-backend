import hashlib
import random
import threading
from dataclasses import dataclass
from logging import Logger, getLogger
from typing import Any, Dict, List, Tuple

MIN_CHROME_BROWSER_VERSION:int=130
MAX_CHROME_BROWSER_VERSION:int=143

SCREEN_RESOLUTIONS:List[Tuple[int,int]] = [
    (1920, 1080), (1920, 1080), (1920, 1080), # Common
    (1366, 768),  (1440, 900),  (1536, 864),  # Laptops
    (2560, 1440), (3840, 2160)                # High Res
]

@dataclass
class BrowserProfile:
    # --- 1. CORE IDENTITY (Dynamic Input) ---
    major_chrome_version: int         # e.g. 125
    full_chrome_version: str          # e.g. "125.0.6422.60"

    # --- 2. HARDWARE FINGERPRINT (NEW) ---
    screen_width: int
    screen_height: int
    cpu_concurrency: int  # e.g., 4, 8, 16
    device_memory: int    # e.g., 4, 8, 16, 32 (GB)

    # --- 3. USER AGENT STRING COMPONENTS (Defaults for Linux/Docker) ---
    mozilla_prefix: str = "Mozilla/5.0"   
    system_information: str = "X11; Linux x86_64"   # "X11; Linux x86_64" is the standard identifier for Chrome on Ubuntu
    platform_engine: str = "AppleWebKit/537.36"     # Engine versions rarely change in modern Chrome strings
    rendering_engine: str = "KHTML, like Gecko"     # Engine versions rarely change in modern Chrome strings
    compatibility_suffix: str = "Safari/537.36"      # The suffix that mimics Safari (standard behavior)

    # --- 4. CLIENT HINTS / METADATA (For CDP Override) ---
    # These MUST match the OS of your Docker Container
    os_platform: str = "Linux"        # Maps to navigator.platform
    os_version: str = "6.5.0"         # A generic, modern Linux Kernel version
    architecture: str = "x86"
    bitness: str = "64"
    mobile_flag: bool = False
    model: str = ""                   # Desktop should always be empty string
    
    @property
    def user_agent_string(self) -> str:
        """
        Constructs the exact UA string.
        Format: Mozilla/5.0 (System) Engine (Rendering) Chrome/Version Safari/Compat
        """
        
        return (
            f"{self.mozilla_prefix} ({self.system_information}) "
            f"{self.platform_engine} ({self.rendering_engine}) "
            f"Chrome/{self.full_chrome_version} {self.compatibility_suffix}"
        )  
    
    @property
    def brands(self) -> List[Dict[str, str]]:
        """
        Generates the 'Grease' brands + Chrome brands for Sec-CH-UA headers.
        """
        return [
            {"brand": "Not/A)Brand", "version": "99"}, 
            {"brand": "Google Chrome", "version": str(self.major_chrome_version)},
            {"brand": "Chromium", "version": str(self.major_chrome_version)}
        ]

    @property
    def cdp_metadata(self) -> Dict[str, Any]:
        """
        Returns the dictionary required for 'Network.setUserAgentOverride'.
        """
        return {
            "brands": self.brands,
            "fullVersion": self.full_chrome_version,
            "platform": self.os_platform,
            "platformVersion": self.os_version,
            "architecture": self.architecture,
            "model": self.model,
            "mobile": self.mobile_flag,
            "bitness": self.bitness,
            "wow64": False
        }
    
  
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
            return cls._instance

        # Singleton instance does not exist, attempt creation with lock.
        with cls._lock:
            if cls._instance is not None:
                return cls._instance

        cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self.logger:Logger = getLogger("user_agent_manager")
        self.min_browser_version=MIN_CHROME_BROWSER_VERSION
        self.max_browser_version=MAX_CHROME_BROWSER_VERSION
    
    def set_max_browser_version(self, major_chrome_version:int) -> None:
        self.max_browser_version = major_chrome_version
        
    def set_min_browser_version(self, major_chrome_version:int) -> None:
        self.min_browser_version = major_chrome_version
    
    def _get_hardware_from_hash(self, hash_int: int) -> Tuple[int, int, int, int]:
        """
        Derives hardware stats deterministically from the hash.
        """
        # 1. Screen Resolution
        res_index = hash_int % len(SCREEN_RESOLUTIONS)
        width, height = SCREEN_RESOLUTIONS[res_index]
        
        # 2. CPU Cores (4, 8, 12, 16)
        # We shift the hash to get a 'fresh' random number
        cpu_seed = (hash_int >> 4) % 4 
        cores = [4, 8, 12, 16][cpu_seed]

        # 3. RAM (4, 8, 16, 32)
        ram_seed = (hash_int >> 8) % 4
        ram = [4, 8, 16, 32][ram_seed]
        
        return width, height, cores, ram
    
    def _get_version_from_hash(self, hash_int: int) -> int:
        version_span = (self.max_browser_version - self.min_browser_version) + 1
        major_version = self.min_browser_version + (hash_int % version_span)
        return major_version
    
    def generate_profile(self, hash_int: int = 0) -> BrowserProfile:
        # Generate hardware stats
        if hash_int == 0:
            # Random for non-sticky
            hash_int = random.getrandbits(32)
            
        major_chrome_version = self._get_version_from_hash(hash_int)
        full_chrome_version:str = f"{major_chrome_version}.0.0.0"
        w, h, cores, ram = self._get_hardware_from_hash(hash_int)

        return BrowserProfile(
            major_chrome_version=major_chrome_version,
            full_chrome_version=full_chrome_version,
            screen_width=w,
            screen_height=h,
            cpu_concurrency=cores,
            device_memory=ram
        )         
        
    def get_sticky_browser_profile(self, proxy_url:str) -> BrowserProfile:
        """
        Returns a user agent based on the proxy url, ensuring the same user agent is used for proxy url every time.
        """
        
        if not proxy_url:
            self.logger.warning("No proxy url passed for sticky! Using default")
            return self.generate_profile()
        
        hash_val = hashlib.sha256(proxy_url.encode('utf-8')).hexdigest()
        hash_int = int(hash_val, 16)
        
        return self.generate_profile(hash_int)

    

user_agent_manager = UserAgentManager()
