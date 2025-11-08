import requests
import random
import json
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor
import datetime

ONE_DAY = 86400

class ProxyHandler:
	"""
	A class that contains all functions related to finding, checking, and rotating proxies
	"""
	
	def __init__(self):
		self.http_proxies = set()
		self.https_proxies = set()
		self.test_url = "http://httpbin.org/ip" 
		self.last_fetched = None
	
	def __fetch_proxifly(self, quantity:int=20, format:str='json'):
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

		# add session header rotation here
		user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.0.0 Safari/537.36'
		api_key = "5VKAL7UXckfUwR4KmFfSBXjhksyKXQc1aU2jzvUgP3nU"
  
		headers = {
          		"Content-Type": "application/json; charset=utf-8",
            		"Authorization" : api_key,
			"User-Agent" : user_agent
              	}
		proxy_dict = {
			"http": "51.159.226.86:443",
			"https": "143.198.202.188:8888",
		}

		http_proxies = []
		https_proxies = []

		try:
			options_http = {
				"format" : format,
				"quantity" : quantity,
				"protocol" : ["http"],
				"https" : False
			}
			response_http = requests.post(proxifly_url, headers=headers, json=options_http, proxies=proxy_dict, timeout=10,verify=False)
			response_http.raise_for_status()
			http_proxies = response_http.json()
			print(f"Proxlify: [+] Successfully fetched {len(http_proxies)} HTTP proxies.")
   
		except requests.exceptions.HTTPError as http_err:
			print(f"Proxlify: [!] HTTP Error while fetching HTTP proxies: {http_err}")
			print(f"Proxlify:\tResponse Body: {response_http.text}")
		except requests.exceptions.RequestException as req_err:
			print(f"Proxlify: [!] Network Error while fetching HTTP proxies: {req_err}")
		except json.JSONDecodeError:
			print("Proxlify: [!] Failed to decode JSON response for HTTP proxies.")

		# get a new proxy here
		proxy_dict = {
			"http": "51.159.226.86:443",
			"https": "143.198.202.188:8888",
		}
		try:
			options_https = {
				"format": format,
				"quantity": quantity,
				"protocol": ["http"],
				"https": True
			}
			response_https = requests.post(proxifly_url, headers=headers, json=options_https, proxies=proxy_dict, timeout=10,verify=False)
			response_https.raise_for_status()
			https_proxies = response_https.json()
			print(f"Proxlify: [+] Successfully fetched {len(https_proxies)} HTTPS proxies.")

		except requests.exceptions.HTTPError as http_err:
			print(f"Proxlify: [!] HTTP Error while fetching HTTPS proxies: {http_err}")
			print(f"Proxlify:\tResponse Body: {response_https.text}")
		except requests.exceptions.RequestException as req_err:
			print(f"Proxlify: [!] Network Error while fetching HTTPS proxies: {req_err}")
		except json.JSONDecodeError:
			print("Proxlify: [!] Failed to decode JSON response for HTTPS proxies.")

		return {
			"http" : [obj["proxy"] for obj in http_proxies],
			"https" : [obj["proxy"] for obj in https_proxies],
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

		http_proxies = []
		https_proxies = []

		try:
			with requests.Session() as session:
				session.headers.update({
					'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36'
				})

				response = session.get(proxy_list_net_url, timeout=10)
				response.raise_for_status()
			soup = BeautifulSoup(response.text, features="html.parser")
			
			# Find the table body, which is a more stable target than the table itself
			table_body = soup.find('tbody')
			if not table_body:
				print("FreeProxyNet: [!] Could not find the proxy table's tbody element. The site layout may have changed.")
				raise ValueError("FreeProxyNet: HTML table body not found")

			rows = table_body.find_all('tr')
   
			for row in rows:
				cols = row.find_all('td')
				cols = [ele.text.strip() for ele in cols]
				if len(cols) > 6:
					ip = cols[0]
					port = cols[1]
					if cols[6] == 'yes':
						https_proxies.append(f"{ip}:{port}")
					else:
						http_proxies.append(f"{ip}:{port}")
				
			if not http_proxies or not https_proxies:
				print("FreeProxyNet: [!] Parsing complete, but no proxy rows were found.")
				return {"http": [], "https": [], "all": []}

			print(f"FreeProxyNet: [+] Successfully scraped {len(http_proxies) + len(https_proxies)} total proxies.")

		except requests.exceptions.RequestException as req_err:
			print(f"FreeProxyNet: [!] Network Error while fetching from free-proxy-list.net: {req_err}")
		except Exception as e:
			print(f"FreeProxyNet: [!] An error occurred during scraping: {e}")

		return {
			"http": http_proxies,
			"https": https_proxies
		}
	
	def __test_proxy(self, proxy: str):
		proxy_dict = {
			"http": proxy,
			"https": proxy,
		}
  
		try:
			response = requests.get(self.test_url, proxies=proxy_dict, timeout=5)
			response.raise_for_status()
			return proxy
		except Exception:
			return None
	
	def __fetch_new_proxies(self):
		

		if self.last_fetched:
			current_datetime = datetime.datetime.now()
			time_difference = (current_datetime - self.last_fetched).total_seconds()	
			if time_difference < ONE_DAY:
				print("[!] Too soon to refetch!")
				return
         
		print("\n--- Starting Proxy Fetch and Validation ---")
		proxifly_urls = self.__fetch_proxifly()
		proxinet_urls = self.__scrape_proxinet_proxies()

		candidate_http = set(proxifly_urls["http"] + proxinet_urls["http"] + list(self.http_proxies))
		candidate_https = set(proxifly_urls["https"] + proxinet_urls["https"] + list(self.https_proxies))

		print(f"[*] Testing {len(candidate_http)} HTTP and {len(candidate_https)} HTTPS candidate proxies...")
	
		valid_http_proxies = set()
		valid_https_proxies = set()


		with ThreadPoolExecutor(max_workers=20) as executor:

			http_results = executor.map(self.__test_proxy, candidate_http)
			for proxy in http_results:
				if proxy:
					valid_http_proxies.add(proxy)
			
			https_results = executor.map(self.__test_proxy, candidate_https)
			for proxy in https_results:
				if proxy:
					valid_https_proxies.add(proxy)

		self.http_proxies = valid_http_proxies
		self.https_proxies = valid_https_proxies
		
		print(f"--- Validation Complete ---")
  
		print(f"Final Proxy list:\n\tHTTP proxies: {len(self.http_proxies)}\n\tHTTPS proxies: {len(self.https_proxies)}")	
  
	def get_proxy(self, protocol="http"):
		target_set = self.https_proxies if protocol == "https" else self.http_proxies

		if not target_set:
			print(f"[*] No valid {protocol} proxies available. Fetching new ones...")
			self.__fetch_new_proxies()
			target_set = self.https_proxies if protocol == "https" else self.http_proxies

		if not target_set:
			print(f"[!] Could not find any valid {protocol} proxies.")
			return None

		return random.choice(list(target_set))


  
if __name__ == "__main__":
    proxy_handler = ProxyHandler()
    
    print("--- Getting an HTTP proxy ---")
    http_proxy = proxy_handler.get_proxy(protocol="http")
    if http_proxy:
        print(f"\n[SUCCESS] Got HTTP Proxy: {http_proxy}\n")
    
    print("--- Getting an HTTPS proxy ---")
    https_proxy = proxy_handler.get_proxy(protocol="https")
    if https_proxy:
        print(f"\n[SUCCESS] Got HTTPS Proxy: {https_proxy}\n")
