import requests
import random
import json
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor
import datetime
import threading
from microservices.web_scraper.config import PROXIFLY_API_KEY
from microservices.web_scraper.managers.user_agent_manager import user_agent_manager
from typing import Dict, List, Set, Optional, Tuple
from common.requests.retry_request import exponential_retry


ONE_DAY_IN_SECONDS = 86400

class ProxyManager:
	"""
	A thread-safe Singleton class that fetches, validates, and rotates proxies
	from multiple sources. It intelligently refreshes its proxy list only when
	needed (i.e., when the list is empty or the data is stale).
	"""
	_instance = None
	_class_lock = threading.Lock()      # guards instance creation
	_init_lock = threading.Lock()       # guards first-time init
	
	def __new__(cls, *args, **kwargs):
		if cls._instance is None:
			with cls._class_lock:
				if cls._instance is None:
					print("ProxyManager instance does not exist. Creating new instance...")
					cls._instance = super().__new__(cls)
		return cls._instance

 
	def __init__(self, 
              	refresh_interval_seconds:int= ONE_DAY_IN_SECONDS,         
              	test_url_http: str = "http://httpbin.org/ip",
        	test_url_https: str = "https://httpbin.org/ip",
         	request_timeout_connect: float = 2.0,
		request_timeout_read: float = 3.0,
		max_workers: int = 40):
         
		if getattr(self, "_initialized", False):
			return
		with self._init_lock:
			if getattr(self, "_initialized", False):
				return

			print("Initializing ProxyManager state for the first time...")
			# Current pool of proxies
			self.http_proxies = set()
			self.https_proxies = set()

			# Config
			self.refresh_interval_seconds = refresh_interval_seconds
			self.test_url_http = test_url_http
			self.test_url_https = test_url_https
			self.timeout = (request_timeout_connect, request_timeout_read)
			self.max_workers = max_workers

			# Concurrency
			self._refresh_lock = threading.Lock()
			self.datetime_last_fetched: Optional[datetime.datetime] = None
   
			self._initialized = True
	
 
	def refresh_now(self):
		with self._refresh_lock:
			self.__perform_full_refresh()


	def reset(self):
		"""Testing aid: clear caches and force next call to rebuild."""
		with self._refresh_lock:
			self.http_proxies.clear()
			self.https_proxies.clear()
			self.datetime_last_fetched = None
            
            
	def get_proxy(self, protocol: str = "http") -> Optional[str]:
		protocol = (protocol or "http").lower()
		if protocol not in ("http", "https"):
			raise ValueError("protocol must be 'http' or 'https'")
		self.__refresh_proxies_if_needed()

		target_set = self.https_proxies if protocol == "https" else self.http_proxies

		if not target_set:
			print(f"[!] Could not find any valid {protocol} proxies after attempting a refresh.")
			return None
		return random.choice(list(target_set))
 
 
	def __refresh_proxies_if_needed(self):
		"""
		Checks if the proxy list needs to be refreshed and triggers it.
		This is the core of the state management logic.
		"""

		if self.__should_refresh():
			with self._refresh_lock:
				# Double-check inside the lock to prevent a race condition
				if self.__should_refresh():
					print("[*] Proxy list is empty or stale. Performing a full refresh...")
					self.__perform_full_refresh()
				else:
					print("[*] Refresh was needed, but another thread completed it. Skipping.")
    
  
	def __should_refresh(self):
		"""Determines if a refresh is required."""
		is_empty = not self.http_proxies and not self.https_proxies
		if self.datetime_last_fetched:
			age = (datetime.datetime.now() - self.datetime_last_fetched).total_seconds()
			return is_empty or age > self.refresh_interval_seconds
		return True

	@staticmethod
	def __normalize_proxy( p: str, scheme: str = "http") -> str:
		p = (p or "").strip()
		if not p:
			return p
		if "://" not in p:
			return f"{scheme}://{p}"
		return p
	@staticmethod
	def __random_two( items: Set[str]) -> Tuple[Optional[str], Optional[str]]:
		if not items:
			return None, None
		if len(items) == 1:
			only = next(iter(items))
			return only, None
		pick = random.sample(list(items), 2)
		return pick[0], pick[1]

	def __perform_full_refresh(self):
		"""
		A single, clear function to build a new set of valid proxies from all sources.
		It builds the new lists completely and then replaces the old ones.
		"""
  
		print("\n--- Full Proxy Refresh ---")
		new_http: Set[str] = set()
		new_https: Set[str] = set()
	
		# Preserving valid proxies that have already been fetched
		if self.http_proxies or self.https_proxies:
			print("[*] Validating currnet saved proxies ...")
			tested_current_proxies = self.__validate_proxies(list(self.http_proxies), list(self.https_proxies))
			new_http.update(tested_current_proxies.get("http", []))
			new_https.update(tested_current_proxies.get("https", []))

  
		# Finding new proxies for bootstrapping
		print("[*] Bootstrapping: Finding proxies at free-proxy-list.net...")
		untested_proxinet_proxies = self.__scrape_proxinet_proxies()
		print("[*] Bootstrapping: Validating proxies from free-proxy-list.net...")
		tested_proxinet_proxies = self.__validate_proxies(untested_proxinet_proxies.get("http", []), untested_proxinet_proxies.get("https", []))
		new_http.update(tested_proxinet_proxies.get("http", []))
		new_https.update(tested_proxinet_proxies.get("https", []))
		
  
		if not new_http and not new_https:
			print("[!] Could not find any valid bootstrap proxies. Skipping Proxifly.")
			self.http_proxies = new_http
			self.https_proxies = new_https
			self.datetime_last_fetched = datetime.datetime.now()
			print(f"Final Proxy list: http={len(self.http_proxies)}, https={len(self.https_proxies)}")
			return
		
  
		# Finding premium proxies from Proxifly
		print(f"[*] Enhancing: Fetching from Proxifly using bootstrap proxy...")
		# --- For HTTP proxies ---
		http1, http2 = self.__random_two(new_http)
		https1, https2 = self.__random_two(new_https)
		
		print(f"Using bootstrapped proxies, \n\tHTTP:  {http1}, {http2}\n\tHTTPS: {https1}, {https2}")
		untested_proxifly_proxies = self.__fetch_proxifly(
			quantity=20,
			format="json",
			proxies_round1={"http": http1, "https": https1} if (http1 or https1) else None,
			proxies_round2={"http": http2, "https": https2} if (http2 or https2) else None,
		)

		print("[*] Enhancing: Validating proxies from Proxifly...")
		tested_proxifly_proxies = self.__validate_proxies(
			untested_proxifly_proxies.get("http", []),
			untested_proxifly_proxies.get("https", []),
		)
		new_http.update(tested_proxifly_proxies.get("http", []))
		new_https.update(tested_proxifly_proxies.get("https", []))

		# Updating proxy set
		self.http_proxies = new_http
		self.https_proxies = new_https
		self.datetime_last_fetched = datetime.datetime.now()
		print(f"Final Proxy list: http={len(self.http_proxies)}, https={len(self.https_proxies)}")
	
 
	def __validate_proxies(self, candidates_http: List[str], candidates_https:List[str]) -> Dict[str, Set[str]]:
		valid_http: Set[str] = set()
		valid_https: Set[str] = set()
		
		with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
			# Map HTTP tasks
			http_results = executor.map(lambda p: self.__test_proxy(p, "http"), candidates_http)
			for proxy in http_results:
				if proxy:
					valid_http.add(proxy)

			# Map HTTPS tasks
			https_results = executor.map(lambda p: self.__test_proxy(p, "https"), candidates_https)
			for proxy in https_results:
				if proxy:
					valid_https.add(proxy)
					
		return {"http": valid_http, "https": valid_https}


	def __test_proxy(self, proxy: str, protocol: str) -> Optional[str]:
		proxy_norm = self.__normalize_proxy(proxy, "http")
		proxies = {"http": proxy_norm, "https": proxy_norm}
		url = self.test_url_http if protocol == "http" else self.test_url_https

		try:
			response = requests.get(url, proxies=proxies, timeout=self.timeout)
			response.raise_for_status()
			return proxy_norm
		except Exception:
			return None


	def __fetch_proxifly(self, quantity:int=20, format:str='json', proxies_round1: Optional[Dict[str, str]] = None, proxies_round2: Optional[Dict[str, str]] = None, max_attempts: int = 3 ) -> Dict[str, List[str]]:
		"""
		Fetches HTTP and HTTPS proxies from the Proxifly API.

		This function makes two separate API calls to get a list of HTTP proxies
		and a list of HTTPS proxies. It is designed to be resilient, so if one
		request fails, it will report the error and continue to attempt the other.

		Args:
			quantity (int): The number of proxies to request for each protocol. Max 20.
			format (str): The desired output format ('json' or 'text').

		Returns:
			dict: A dictionary containing the lists of proxies.
			e.g., {"http": [...], "https": [...]}
			Returns empty lists for failed requests.
  		"""	
		"""
		var options = {
			protocol: 'http', // http | socks4 | socks5
			anonymity: 'elite', // transparent | anonymous | elite
			country: 'US', // https://www.nationsonline.org/oneworld/country_code_list.htm
			https: true, // true | false
			speed: 10000, // 0 - 60000
			format: 'json', // json | text
			quantity: 1, // 1 - 20
		};
		"""

		proxifly_url = "https://api.proxifly.dev/proxy"
	  
		def fetch(https_flag: bool, bootstrap_proxies: Optional[Dict[str, str]]) -> List[str]:
			
			options = {
				"format" : format,
				"quantity" : max(1, min(20, int(quantity))),
				"protocol" : ["http"],
				"https" : https_flag
			}
   
			headers = {
				"Content-Type": "application/json; charset=utf-8",
				"Authorization" : PROXIFLY_API_KEY,
				"User-Agent" : user_agent_manager.get_random_agent()
			}
			try:
				response = requests.post(proxifly_url, headers=headers, json=options, proxies=bootstrap_proxies, timeout=self.timeout)
				# could check for status code here, and set a time for next proxifly fetch
				response.raise_for_status()
				data = response.json()
    
				if not isinstance(data, list):
					raise Exception("Garbled data from Proxifly")
    
				print(f"Proxlify: [+] Successfully fetched {len(data)} HTTP proxies.")
				return [self.__normalize_proxy(x["proxy"]) for x in data]
				
			except requests.exceptions.HTTPError as http_err:
				print(f"Proxlify: [!] HTTP Error while fetching HTTP proxies: {http_err}")
				print(f"Proxlify:\tResponse Body: {response.text}")
				return []
			except requests.exceptions.RequestException as req_err:
				print(f"Proxlify: [!] Network Error while fetching HTTP proxies: {req_err}")
				return []
			except json.JSONDecodeError:
				print("Proxlify: [!] Failed to decode JSON response for HTTP proxies.")
				return []
		
		http_proxies = fetch(False, proxies_round1)
		https_proxies = fetch(True, proxies_round2)

		return {
			"http" : http_proxies + https_proxies,
			"https" : https_proxies,
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
			"User-Agent" : user_agent_manager.get_random_agent(),
			"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
              	}
  
		http_proxies: Set[str] = set()
		https_proxies: Set[str] = set()

		try:
			with requests.Session() as session:
				session.headers.update(headers)
				response = session.get(proxy_list_net_url, timeout=self.timeout)
				response.raise_for_status()
    
			soup = BeautifulSoup(response.text, features="html.parser")
			
			tbody = soup.find('tbody')
			if not tbody:
				print("FreeProxyNet: [!] Could not find the proxy table's tbody element. The site layout may have changed.")
				raise ValueError("FreeProxyNet: HTML table body not found")

			rows = tbody.find_all('tr')
   
			for row in rows:
				cols = [td.text.strip() for td in row.find_all("td")]
				if len(cols) < 6: 
					continue
				ip, port, https_flag = cols[0], cols[1], cols[6].lower()
				proxy_no_scheme = f"{ip}:{port}"
    
				http_proxies.add(self.__normalize_proxy(proxy_no_scheme, scheme="http"))
				if https_flag == "yes":
					https_proxies.add(self.__normalize_proxy(proxy_no_scheme, scheme="http"))  # requests uses http scheme for proxy

			total = len(http_proxies | https_proxies)
			print(f"FreeProxyList: scraped {total} proxies (http: { len(http_proxies)}, https: {len(https_proxies)})")

		except requests.exceptions.RequestException as req_err:
			print(f"FreeProxyNet: [!] Network Error while fetching from free-proxy-list.net: {req_err}")
		except Exception as e:
			print(f"FreeProxyNet: [!] An error occurred during scraping: {e}")

		return {
			"http": list(http_proxies),
			"https": list(https_proxies)
		}
	
	

if __name__ == "__main__":
    proxy_handler = ProxyManager()
    
    print("--- Getting an HTTP proxy ---")
    http_proxy = proxy_handler.get_proxy(protocol="http")
    if http_proxy:
        print(f"\n[SUCCESS] Got HTTP Proxy: {http_proxy}\n")
    
    print("--- Getting an HTTPS proxy ---")
    https_proxy = proxy_handler.get_proxy(protocol="https")
    if https_proxy:
        print(f"\n[SUCCESS] Got HTTPS Proxy: {https_proxy}\n")

# proxy_manager = ProxyManager()
