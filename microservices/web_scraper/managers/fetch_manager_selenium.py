import threading
from typing import Dict, Tuple

import requests
from requests.exceptions import RequestException
import socket
 
from common.requests.retry_request import exponential_retry
from microservices.web_scraper.managers.proxy_manager_paid import proxy_manager_paid, ProxyManagerPaid
from microservices.web_scraper.managers.proxy_manager import ProxyManager
from microservices.web_scraper.managers.user_agent_manager import user_agent_manager
from microservices.web_scraper.config import MAX_FETCH_RETRIES, INITIAL_FETCH_DELAY_S, FETCH_DELAY_GROWTH_RATE
import tempfile
import shutil
import os
from seleniumwire import undetected_chromedriver as uc
from selenium.common.exceptions import WebDriverException
import time
import traceback

class FetchManagerSelenium:
    """
    A thread-safe Singleton class that fetches news URLs.
    """

    _instance = None
    _class_lock = threading.Lock()  # guards instance creation
    _init_lock = threading.Lock()  # guards first-time init
    _startup_lock = threading.Lock() # for staggering
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._class_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, default_timeout=(15.0, 20.0), proxy_manager=None):
        if getattr(self, "_initialized", False): return
        self.proxy_manager = proxy_manager
        # Pre-create the selenium-wire CA folder to prevent the 'PEM routines' error
        os.makedirs(os.path.expanduser("~/.seleniumwire"), exist_ok=True)
        self._initialized = True

    @staticmethod
    def get_headers_for_country(country_code:str = 'US'):
        language_options = {
            # Canada: English first, then French (since it's bilingual)
            'CA': 'en-CA,en;q=0.9,fr-CA;q=0.8',
            
            # United Kingdom: British English preferred
            'GB': 'en-GB,en;q=0.9',
            
            # United States: American English preferred
            'US': 'en-US,en;q=0.9',
            
            # France: English first (for content), French second (for proxy-matching stealth)
            'FR': 'en-US,en;q=0.9,fr-FR;q=0.8,fr;q=0.7',
        }
        default_string = language_options['US']
        return language_options.get(country_code.upper(), default_string)

    @staticmethod
    def find_free_port():
        """Finds a truly free port for the selenium-wire proxy to bind to."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', 0))
            s.listen(1)
            port = s.getsockname()[1]
        return port
    
    def _create_enhanced_headers(self, accept_language: str = "en-US,en;q=0.9") -> Dict[str, str]:
        """Returns a dictionary of headers to better mimic a real browser."""        
        return {
            "Referer" : 'https://www.google.com/',
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
            "Accept-Language": accept_language,
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
        }
    
    
    def generate_interceptor_function(self, custom_headers: Dict[str, str]):
        def interceptor(request):
            """Intercepts request made by Selenium and replaces headers. Returns a dictionary of headers to better mimic a real browser."""
            if request.headers.get('Sec-Fetch-Dest') == 'document':
                for key, value in custom_headers.items():
                    if key in request.headers:
                        del request.headers[key]
                    request.headers[key] = value

        return interceptor
        

    def get_clean_driver(self, proxy_url, user_agent, custom_headers):
        
        wire_port = self.find_free_port()
        debug_port = self.find_free_port() 
        
        user_data_dir = tempfile.mkdtemp(prefix="chrome_profile_")
        wire_tmp_dir = tempfile.mkdtemp(prefix="wire_")
        
        options = uc.ChromeOptions()
        options.add_argument('--headless') # Most news sites require headless in Docker
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--ignore-certificate-errors')
        
        options.add_argument(f'--remote-debugging-port={debug_port}')
        options.add_argument(f'--user-data-dir={user_data_dir}')
        
        options.add_argument(f'--user-agent={user_agent}')
        options.binary_location = "/usr/bin/google-chrome"
                
        proxy_options = {
            'proxy': {'http': proxy_url, 'https': proxy_url},
            'port': wire_port,
            'request_storage_base_dir': wire_tmp_dir,
            'request_storage': 'memory',
            'verify_ssl': False,
        }
        
        with self._startup_lock:
            try:
                driver = uc.Chrome(
                    options=options, 
                    seleniumwire_options=proxy_options,
                    headless=True, 
                    use_subprocess=True, # Recommended for Docker
                    # This prevents threads from fighting over the same driver file
                    driver_executable_path=None 
                )
                # CRITICAL: Wait for the session to actually be "ready"
                time.sleep(4) 
            except Exception as e:
                # Cleanup immediately if boot fails
                shutil.rmtree(user_data_dir, ignore_errors=True)
                shutil.rmtree(wire_tmp_dir, ignore_errors=True)
                raise e
                
        driver.set_page_load_timeout(60)
        driver.thread_dirs = [user_data_dir, wire_tmp_dir]
        driver.request_interceptor = self.generate_interceptor_function(custom_headers)
        
        return driver
    
    def handle_scroll(driver):
        pass
    
    def handle_pop_ups(driver):
        pass
    
    
    @exponential_retry(
        max_attempts=MAX_FETCH_RETRIES,
        initial_delay_s=INITIAL_FETCH_DELAY_S,
        growth_rate=FETCH_DELAY_GROWTH_RATE,
        jitter=True,
        on_exceptions=(RequestException, WebDriverException, Exception),
    )
    def fetch_article_html(self, url: str):
        """
        Fetches the HTML of a webpage using rotating headers and proxies.
        This method is wrapped by a retry decorator. It is responsible for
        a SINGLE fetch attempt and for reporting bad proxies.
        """
        driver = None
        proxy_url = None
        
        try:
            
            proxies = self.proxy_manager.get_next_proxy()
            if proxies is None:
                raise Exception("Proxy manager returned None - Pool might be empty")
            
            proxy_url = proxies.get("https", proxies.get("http"))
            if not proxy_url:
                raise Exception("Proxy dictionary found, but no http/https URL present")

            mapping = self.proxy_manager.ip_country_mapping
            if mapping is None: 
                mapping = {} 
                print("NO mapping found")
                
            country_code = mapping.get(proxy_url, "US")
            lang_string = self.get_headers_for_country(country_code)
            custom_headers = self._create_enhanced_headers(lang_string)
            user_agent = user_agent_manager.get_random_agent()
            
            
            
            driver = self.get_clean_driver(proxy_url, user_agent, custom_headers)
            driver.get(url)
            
            
            # Optional: Add your scroll/popup logic here
            # self.handle_pop_ups(driver)
            # self.handle_scroll(driver)
            html = driver.page_source
            if "ERR_CERT_AUTHORITY_INVALID" in html:
                raise Exception("SSL Bypass failed")
            print(f"[SUCCESS] Successfully fetched {url}")
            return html

        except Exception as e:
            print(f"[ERROR] Fetching {url}: {e}")
            traceback.print_exc()
            raise e
        finally:
            if driver:
                # Get the tmp dir we created
                dirs_to_clean = getattr(driver, 'thread_dirs', [])

                # Clean up the folder after driver closes
                try:
                    driver.quit()
                    for d in dirs_to_clean:
                        if os.path.exists(d):
                            shutil.rmtree(d, ignore_errors=True)
                except Exception as cleanup_err:
                    print(f"Cleanup error: {cleanup_err}")


fetch_manager = FetchManagerSelenium(proxy_manager=proxy_manager_paid)
