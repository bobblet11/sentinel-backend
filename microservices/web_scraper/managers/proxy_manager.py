import datetime
import json
import os
import random
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Set, Tuple

import requests
from bs4 import BeautifulSoup

from microservices.web_scraper.managers.user_agent_manager import user_agent_manager

try:
    import socks 
    print("[*] PySocks installed")
except ImportError:
    print("[!] PySocks not installed; SOCKS proxies will always fail. Run: pip install pysocks")

ONE_DAY_IN_SECONDS = 86400
DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S'
MIN_HTTPS_SOCKS4_SOCKS5_NUMBER = 10
class ProxyManager:
    """
    A thread-safe Singleton class that fetches, validates, and rotates proxies
    from multiple sources. It intelligently refreshes its proxy list only when
    needed (i.e., when the list is empty or the data is stale).
    """

    _instance = None
    _class_lock = threading.Lock()  # guards instance creation
    _init_lock = threading.Lock()  # guards first-time init

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._class_lock:
                if cls._instance is None:
                    print(
                        "ProxyManager instance does not exist. Creating new instance..."
                    )
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
        self,
        refresh_interval_seconds: int = ONE_DAY_IN_SECONDS,
        test_url_http: str = "http://httpbin.org/ip",
        test_url_https: str = "https://httpbin.org/ip",
        request_timeout_connect: float = 8.0,
        request_timeout_read: float = 12.0,
        max_workers: int = 40,
    ):

        if getattr(self, "_initialized", False):
            return
        
        with self._init_lock:
            if getattr(self, "_initialized", False):
                return

            print("Initializing ProxyManager state for the first time...")
            # Current pool of proxies
            self.https_proxies:Set[str] = set()
            self.socks4_proxies:Set[str] = set()
            self.socks5_proxies:Set[str] = set()
            self.usable_proxies:Set[str] = set()
            
            # Config
            self.refresh_interval_seconds = refresh_interval_seconds
            self.test_url_http = test_url_http
            self.test_url_https = test_url_https
            self.timeout = (request_timeout_connect, request_timeout_read)
            self.max_workers = max_workers

            # Concurrency
            self._refresh_lock = threading.Lock()
            self.datetime_last_fetched: Optional[datetime.datetime] = None

            script_dir = os.path.dirname(os.path.abspath(__file__))
            self.saved_proxies_json_path = os.path.join(script_dir, "proxies.json")

            print("[*] Loading Saved Proxies")
            if os.path.exists(self.saved_proxies_json_path):
                with open(self.saved_proxies_json_path, "r") as file:
                    proxies: Dict[str, List[str]] = json.load(file)
                    self.https_proxies.update(proxies.get("https", []))
                    self.socks4_proxies.update(proxies.get("socks4", []))
                    self.socks5_proxies.update(proxies.get("socks5", []))
                    datetime_str: Optional[str] = proxies.get("datetime_last_fetched")
                    
                    if datetime_str:
                        try:
                            self.datetime_last_fetched = datetime.datetime.strptime(datetime_str, DATETIME_FORMAT)
                        except ValueError:
                            self.datetime_last_fetched = None
            else:
                print("[*] No saved proxies file found; starting fresh.")
                    
            print("[*] Validating Loaded Proxies")
            valid_stored_proxies = self.__validate_proxies(self.https_proxies, self.socks4_proxies, self.socks5_proxies)
            self.https_proxies = valid_stored_proxies.get("https", set())
            self.socks4_proxies = valid_stored_proxies.get("socks4", set())
            self.socks5_proxies = valid_stored_proxies.get("socks5", set())
            
            print(f"[*] Validated!:\n\thttps: {len(self.https_proxies)}\n\tsocks4: {len(self.socks4_proxies)}\n\tsocks5: {len(self.socks5_proxies)}")
            self._initialized = True

    def refresh_now(self) -> None:
        with self._refresh_lock:
            self.__perform_full_refresh()

    def reset(self) -> None:
        """Testing aid: clear caches and force next call to rebuild."""
        with self._refresh_lock:
            self.https_proxies.clear()
            self.socks4_proxies.clear()
            self.socks5_proxies.clear()
            self.datetime_last_fetched = None
            
            
    def get_proxy(self) -> Optional[str]:
        self.__refresh_proxies_if_needed()

        if self.usable_proxies:
            return random.choice(list(self.usable_proxies))
        
        print("[!] Could not find any valid proxies.")
        return None

    def __refresh_proxies_if_needed(self) -> None:
        """
        Checks if the proxy list needs to be refreshed and triggers it.
        This is the core of the state management logic.
        """

        if not self.__should_refresh():
                print("[*] Refresh not needed.")
                return
            
        with self._refresh_lock:
            # Double-check inside the lock to prevent a race condition
            if not self.__should_refresh():
                print(
                    "[*] Refresh was needed, but another thread completed it. Skipping."
                )
                return
            
            print(
                "[*] Proxy list is empty or stale. Performing a full refresh..."
            )
            self.__perform_full_refresh()
    

    def __should_refresh(self) -> bool:
        """Determines if a refresh is required."""
        capable_proxies_count  =  (len(self.https_proxies) + len(self.socks4_proxies) + len(self.socks5_proxies))
        is_too_low = capable_proxies_count < MIN_HTTPS_SOCKS4_SOCKS5_NUMBER
        if self.datetime_last_fetched:
            age = (datetime.datetime.now() - self.datetime_last_fetched).total_seconds()
            return is_too_low or age > self.refresh_interval_seconds
        return True

    @staticmethod
    def __normalize_proxy(p: str, scheme: str = "https") -> str:
        p = (p or "").strip()
        if not p:
            return p
        if "://" not in p:
            return f"{scheme}://{p}"
        return p

    @staticmethod
    def __random_two(items: Set[str]) -> Tuple[Optional[str], Optional[str]]:
        if not items:
            return None, None
        if len(items) == 1:
            only = next(iter(items))
            return only, only
        pick = random.sample(list(items), 2)
        return pick[0], pick[1]
    
    
    @staticmethod    
    def __random_three(items: Set[str]) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        lst = list(items)
        n = len(lst)
        if n == 0:
            return None, None, None
        if n >= 3:
            pick = random.sample(lst, 3)
            return pick[0], pick[1], pick[2]
        out = []
        while len(out) < 3:
            out.append(random.choice(lst))
        return tuple(out)  # type: ignore
    
    @staticmethod
    def __random_four(items: Set[str]) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
        lst = list(items)
        n = len(lst)
        if n == 0:
            return None, None, None, None
        if n >= 4:
            pick = random.sample(lst, 4)
            return pick[0], pick[1], pick[2], pick[3]
        # If less than 4, cycle without bias
        out = []
        while len(out) < 4:
            out.append(random.choice(lst))
        return tuple(out)  # type: ignore

    def __perform_full_refresh(self) -> None:
        """
        A single, clear function to build a new set of valid proxies from all sources.
        It builds the new lists completely and then replaces the old ones.
        """

        print("\n--- Full Proxy Refresh ---")
        new_https: Set[str] = set()
        new_socks4: Set[str] = set()
        new_socks5: Set[str] = set()

        # Preserving valid proxies that have already been fetched
        print("[*] Validating currnet saved proxies ...")
        tested_current_proxies = self.__validate_proxies(self.https_proxies, self.socks4_proxies, self.socks5_proxies)
        new_https.update(tested_current_proxies.get("https", []))
        new_socks4.update(tested_current_proxies.get("socks4", []))
        new_socks5.update(tested_current_proxies.get("socks5", []))
        print(f"Total proxies:\n\thttps={len(new_https)}\n\tsocks4={len(new_socks4)}\n\tsocks5={len(new_socks5)}")
        
        # Finding new proxies for bootstrapping
        print("[*] Bootstrapping: Finding proxies at free-proxy-list.net...")
        untested_proxinet_proxies = self.__scrape_proxinet_proxies()
        print("[*] Bootstrapping: Validating proxies from free-proxy-list.net...")
        tested_proxinet_proxies = self.__validate_proxies(
            untested_proxinet_proxies.get("https", []),
            [],
            []
        )
        new_https.update(tested_proxinet_proxies.get("https", []))
        print(f"Total proxies:\n\thttps={len(new_https)}\n\tsocks4={len(new_socks4)}\n\tsocks5={len(new_socks5)}")
        
        https1, https2, https3 = None, None, None
        
        if not new_https and not new_socks4 and not new_socks5:
            print("[!] Enhancing: Could not find any valid bootstrap proxies. Using actual IP on Proxifly.")
        else:
            # Finding premium proxies from Proxifly
            print("[*] Enhancing: Fetching from Proxifly using bootstrap proxy...")
            # --- For HTTP proxies ---
            https1, https2, https3 = self.__random_three(new_https.union(new_socks4).union(new_socks5))
            print(
                f"Using bootstrapped proxies, \nHTTPS:\n\t{https1}, \n\t{https2}, \n\t{https3}"
            )
            
        untested_proxifly_proxies = self.__fetch_proxifly(
            proxies_round1=(
                {"http": https1, "https": https1}
                if (https1)
                else None
            ),
            proxies_round2=(
                {"http": https2, "https": https2}
                if (https2)
                else None
            ),
            proxies_round3=(
                {"http": https3, "https": https3}
                if (https3)
                else None
            )
        )

        print("[*] Enhancing: Validating proxies from Proxifly...")
        tested_proxifly_proxies = self.__validate_proxies(
            untested_proxifly_proxies.get("https", []),
            untested_proxifly_proxies.get("socks4", []),
            untested_proxifly_proxies.get("socks5", []),
        )
        new_https.update(tested_proxifly_proxies.get("https", []))
        new_socks4.update(tested_proxifly_proxies.get("socks4", []))
        new_socks5.update(tested_proxifly_proxies.get("socks5", []))
                
        # Updating proxy set
        self.https_proxies = new_https
        self.socks4_proxies = new_socks4
        self.socks5_proxies = new_socks5
        self.usable_proxies = self.https_proxies.union(self.socks4_proxies).union(self.socks5_proxies)
        self.datetime_last_fetched = datetime.datetime.now()

        # Saving proxy set
        with open(self.saved_proxies_json_path, "w") as file:
            proxies: str = json.dumps(
                {
                 "https": list(self.https_proxies), 
                 "socks4": list(self.socks4_proxies),
                 "socks5": list(self.socks5_proxies),
                 "usable_proxies" : list(self.usable_proxies),
                 "datetime_last_fetched" : self.datetime_last_fetched.strftime(DATETIME_FORMAT)},
                indent=4,
            )
            file.write(proxies)
        
        print(f"Final proxies:\n\thttps={len(new_https)}\n\tsocks4={len(new_socks4)}\n\tsocks5={len(new_socks5)}")

    def __validate_proxies(
        self, candidates_https: List[str], candidates_socks4: List[str], candidates_socks5: List[str]
    ) -> Dict[str, Set[str]]:
        valid_https: Set[str] = set()
        valid_socks4: Set[str] = set()
        valid_socks5: Set[str] = set()
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Map HTTPS tasks
            https_results = executor.map(
                lambda p: self.__test_proxy(p, "https"), candidates_https
            )
            for proxy in https_results:
                if proxy:
                    valid_https.add(proxy)
                    
            # Map SOCKs4 tasks
            socks4_results = executor.map(
                lambda p: self.__test_proxy(p, "socks4"), candidates_socks4
            )
            for proxy in socks4_results:
                if proxy:
                    valid_socks4.add(proxy)
                    
            # Map SOCKs5 tasks
            socks5_results = executor.map(
                lambda p: self.__test_proxy(p, "socks5"), candidates_socks5
            )
            for proxy in socks5_results:
                if proxy:
                    valid_socks5.add(proxy)

        return { "https": valid_https, "socks4": valid_socks4, "socks5": valid_socks5}

    def __test_proxy(self, proxy: str, protocol: str) -> Optional[str]:
        # protocol is one of: "http", "https", "socks4", "socks5"
        if protocol in ("http", "https"):
            # Use http scheme in requests proxy URL even for https-capable HTTP proxies
            proxy_norm = self.__normalize_proxy(proxy, "http")
            proxies = {"http": proxy_norm, "https": proxy_norm}
            url = self.test_url_http if protocol == "http" else self.test_url_https
        elif protocol == "socks4":
            # requests needs PySocks and scheme socks4://
            proxy_norm = self.__normalize_proxy(proxy, "socks4")
            proxies = {"http": proxy_norm, "https": proxy_norm}
            url = self.test_url_https
        elif protocol == "socks5":
            # Use socks5h to resolve hostnames via proxy
            proxy_norm = self.__normalize_proxy(proxy, "socks5")
            proxies = {"http": proxy_norm, "https": proxy_norm}
            url = self.test_url_https
        else:
            return None

        try:
            response = requests.get(url, proxies=proxies, timeout=self.timeout)
            response.raise_for_status()
            return proxy_norm
        except Exception:
            return None

    def __fetch_proxifly(
        self,
        proxies_round1: Optional[Dict[str, str]] = None,
        proxies_round2: Optional[Dict[str, str]] = None,
        proxies_round3: Optional[Dict[str, str]] = None,
    ) -> Dict[str, List[str]]:
        """
        Fetches HTTP,HTTPS,SOCKS4, SOCKS5 proxies from the Proxifly API.

        This function makes 4 separate API calls to get a list of proxies. 
        It is designed to be resilient, so if one request fails, it will 
        report the error and continue to attempt the other.

        Returns:
                dict: A dictionary containing the lists of proxies.
                e.g., {"http": [...], "https": [...], "socks4": [...], "socks5" : [...]}
                Returns empty lists for failed requests.
        """

        # proxifly_http_url = "https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/protocols/http/data.txt"
        proxifly_https_url = "https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/protocols/https/data.txt"
        proxifly_socks4_url = "https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/protocols/socks4/data.txt"
        proxifly_socks5_url = "https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/protocols/socks5/data.txt"
        
        def fetch(
            url: str, bootstrap_proxies: Optional[Dict[str, str]], proxy_type: str
        ) -> List[str]:

            headers = {
                "Content-Type": "text/html; charset=utf-8",
                "User-Agent": user_agent_manager.get_random_agent(),
            }
            
            try:
                response = requests.get(
                    url,
                    headers=headers,
                    proxies=bootstrap_proxies,
                    timeout=(10,10),
                )
                # could check for status code here, and set a time for next proxifly fetch
                response.raise_for_status()
                raw_text = response.text
                
                if not isinstance(raw_text, str):
                    raise Exception("Garbled data from Proxifly")
                
                lines = raw_text.splitlines()
                proxy_list = [line.strip() for line in lines if line.strip()]
                print(f"Proxlify: [+] Successfully fetched {len(proxy_list)} {proxy_type} proxies.")
                return proxy_list

            except requests.exceptions.HTTPError as http_err:
                print(
                    f"Proxlify: [!] HTTP Error while fetching HTTP proxies: {http_err}"
                )
                print(f"Proxlify:\tResponse Body: {response.text}")
                return []
            except requests.exceptions.RequestException as req_err:
                print(
                    f"Proxlify: [!] Network Error while fetching HTTP proxies: {req_err}"
                )
                return []
            except json.JSONDecodeError:
                print("Proxlify: [!] Failed to decode JSON response for HTTP proxies.")
                return []

        https_proxies = fetch(proxifly_https_url, proxies_round1, proxy_type="HTTPS")
        socks4_proxies = fetch(proxifly_socks4_url, proxies_round2, proxy_type="SOCKS4")
        socks5_proxies = fetch(proxifly_socks5_url, proxies_round3, proxy_type="SOCKS5")

        return {
            "https": https_proxies,
            "socks4": socks4_proxies,
            "socks5": socks5_proxies,
        }

    def __scrape_proxinet_proxies(self):
        """
        Fetches HTTP and HTTPS proxies from the free-proxy-list.net website.

        This scrapes table from the website, breaks its table apart, and extracts the proxies.

        Returns:
                dict: A dictionary containing the lists of proxies.
                e.g., {"http": [...], "https": [...]}
                Returns empty lists for failed requests.
        """

        proxy_list_net_url = "https://free-proxy-list.net/"
        headers = {
            "Content-Type": "text/html ",
            "User-Agent": user_agent_manager.get_random_agent(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

        https_proxies: Set[str] = set()

        try:
            with requests.Session() as session:
                session.headers.update(headers)
                response = session.get(proxy_list_net_url, timeout=self.timeout)
                response.raise_for_status()

            soup = BeautifulSoup(response.text, features="html.parser")

            tbody = soup.find("tbody")
            if not tbody:
                print(
                    "FreeProxyNet: [!] Could not find the proxy table's tbody element. The site layout may have changed."
                )
                raise ValueError("FreeProxyNet: HTML table body not found")

            rows = tbody.find_all("tr")

            for row in rows:
                cols = [td.text.strip() for td in row.find_all("td")]
                if len(cols) < 6:
                    continue
                ip, port, https_flag = cols[0], cols[1], cols[6].lower()
                proxy_no_scheme = f"{ip}:{port}"

                if https_flag == "yes":
                    https_proxies.add(
                        self.__normalize_proxy(proxy_no_scheme, scheme="http")
                    )  # requests uses http scheme for proxy
                    
            print(
                f"FreeProxyList: scraped https proxies: {len(https_proxies)})"
            )

        except requests.exceptions.RequestException as req_err:
            print(
                f"FreeProxyNet: [!] Network Error while fetching from free-proxy-list.net: {req_err}"
            )
        except Exception as e:
            print(f"FreeProxyNet: [!] An error occurred during scraping: {e}")

        return {"https": list(https_proxies)}


if __name__ == "__main__":
    
    proxy_handler = ProxyManager()

    print("--- Getting a proxy ---")
    http_proxy = proxy_handler.get_proxy()
    if http_proxy:
        print(f"\n[SUCCESS] Got Proxy: {http_proxy}\n")

# proxy_manager = ProxyManager()
