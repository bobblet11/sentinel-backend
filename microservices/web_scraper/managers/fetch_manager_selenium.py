import threading
from typing import Dict, Tuple, List

import requests
from requests.exceptions import RequestException
import socket
import json
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
from seleniumwire import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementClickInterceptedException

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

    def __init__(self, default_timeout=(15.0, 20.0), proxy_manager=None, hint_path:str="./combined_hints.json", screenshots_path="./"):
        if getattr(self, "_initialized", False): return
        self.proxy_manager = proxy_manager
        # Pre-create the selenium-wire CA folder to prevent the 'PEM routines' error
        os.makedirs(os.path.expanduser("~/.seleniumwire"), exist_ok=True)
        
        with open(hint_path, 'r') as f:
            hint_config: Dict[str,str] = json.load(f)
            self.x_paths: Dict[str, List[str]] = self.generate_xpath_dict(hint_config)
            
        self.screenshots_path = screenshots_path
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
        # --- ISOLATION STEP 1: Unique Port & Dirs ---
        wire_port = self.find_free_port()
        debug_port = self.find_free_port()
        user_data_dir = tempfile.mkdtemp(prefix="chrome_profile_")
        wire_tmp_dir = tempfile.mkdtemp(prefix="wire_")
        
        # --- ISOLATION STEP 2: Unique Driver Binary (THE FIX) ---
        # Create a unique folder and COPY the system chromedriver into it.
        # This prevents UC from colliding on the patched file.
        driver_executable_dir = tempfile.mkdtemp(prefix="driver_exe_")
        # Note: Ensure the path matches where Chrome/Chromedriver is installed in your Dockerfile
        base_driver_path = "/usr/bin/chromedriver" 
        unique_driver_path = os.path.join(driver_executable_dir, "chromedriver")
        shutil.copy2(base_driver_path, unique_driver_path)
        os.chmod(unique_driver_path, 0o755) # Make executable

        options = uc.ChromeOptions()
        options.add_argument('--headless')
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
            'verify_ssl': False
        }

        # --- ISOLATION STEP 3: Strict Creation Lock ---
        with self._startup_lock:
            driver = uc.Chrome(
                options=options,
                seleniumwire_options=proxy_options,
                # Point UC to our private copy of the driver
                driver_executable_path=unique_driver_path, 
                headless=True,
                # use_subprocess is buggy in some multi-threaded Docker setups; 
                # let's set it to False to see if stability improves.
                use_subprocess=False 
            )
            time.sleep(3) # Give the OS time to bind the ports

        # Store all 3 directories for cleanup
        driver._thread_dirs = [user_data_dir, wire_tmp_dir, driver_executable_dir]
        driver.request_interceptor = self.generate_interceptor_function(custom_headers)
        return driver
    
    def extract_source_name(self, url:str):
        source_map: Dict[str,str] = {
            ("abcnews", "abcnews.go.com"):"ABC",
            ("bbc", "www.bbc.com"):"BBC",
            ("cbc", "www.cbc.ca"):"CBC",
            ("cbs", "www.cbsnews.com"):"CBS",
            ("euronews", "www.euronews.com"):"Euronews",
            ("nbcnews", "www.nbcnews.com"):"NBC",
            ("npr","www.npr.org"):"NPR",
            ("theguardian","www.theguardian.com"):"The_Guardian",
        }
        
        for url_patterns, source_name in source_map.items():
            for pattern in url_patterns:
                if pattern in url:
                    return source_name
                
        return None
    
    def _build_xpath(self, rule_name, rule_data):
        """
        Converts the JSON rule into a valid XPath string.
        """
        
        print(f"Creating xpath for {rule_name}")
        xpath_parts = []

        # 1. Handle Parents (Ancestors)
        # Your JSON lists immediate parent first, so we reverse it to build XPath Top-Down
        if "parents" in rule_data:
            for parent in reversed(rule_data["parents"]):
                tag = parent.get("tag", "*")
                attrs = self._get_attribute_predicates(parent)
                
                # Combine tag and attributes, e.g., //div[@id='onetrust']
                xpath_parts.append(f"//{tag}{attrs}")

        # 2. Handle the Target Element
        tag = rule_data.get("tag", "*")
        attrs = self._get_attribute_predicates(rule_data)
        xpath_parts.append(f"//{tag}{attrs}")
        print(f"Xpath for {rule_name} = {xpath_parts}")
        # Join parts to form full path: //ancestor//parent//target
        return "".join(xpath_parts)
    
    def _get_attribute_predicates(self, data):
        """
        Helper to turn a dictionary {"class": "foo", "id": "bar"} 
        into XPath string "[contains(@class, 'foo') and @id='bar']"
        """
        predicates = []
        
        # Keys to ignore (not HTML attributes)
        ignore_keys = ["tag", "parents"]

        for key, value in data.items():
            if key in ignore_keys:
                continue
            
            # Special handling for 'class' to allow partial matches
            if key == "class":
                predicates.append(f"contains(@class, '{value}')")
            elif key == "text_contains":
                # This generates XPath: //button[contains(text(), 'Maybe later')]
                predicates.append(f"contains(., '{value}')") 
            else:
                # specific attributes like ng-click, external-event, etc.
                predicates.append(f"@{key}='{value}'")

        if not predicates:
            return ""
        
        return "[" + " and ".join(predicates) + "]"
    
    def handle_scroll(self, driver):
        print("Scrolling down...")
        last_height = driver.execute_script("return document.body.scrollHeight")
        while True:
            driver.execute_script("window.scrollBy(0, 800);")
            time.sleep(5) 
            
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height
        print("Reached the bottom!")
    
    def generate_xpath_dict(self, hint_config):
        """
        Generates a map of all the close buttons needed to be pressed for each source.
        """
        xpath_dict = {}
        for source_name, source_rules in hint_config.items():
            xpath_dict[source_name] = []
            
            for rule_name, rule_data in source_rules.get("selectors", {}).items():
                print(rule_name, rule_data)
                xpath = self._build_xpath(rule_name, rule_data)
                xpath_dict[source_name].append(xpath)
        
        return xpath_dict
            
    def handle_pop_ups(self, source_name:str, driver):
        print(f"Looking for pop ups for {source_name}")
        x_paths = self.x_paths.get(source_name, [])
        
        if not x_paths:
            print(f"No xpath rules found for {source_name}")
            return
        
        def try_click(context_driver, xpath):
            print(f"trying to click {xpath}")
            try:
                # Reduced timeout to 1s because we iterate iframes, don't want to wait long per frame
                element = WebDriverWait(context_driver, 1).until(
                    EC.presence_of_element_located((By.XPATH, xpath))
                )
                if element.is_displayed():
                    print(f"   Found popup [{xpath}]. Clicking...")
                    try:
                        element.click()
                    except ElementClickInterceptedException:
                        context_driver.execute_script("arguments[0].click();", element)
                    print(f"   ✅ Closed [{xpath}]")
                    return True
            except TimeoutException:
                pass
            except Exception as e:
                print(f"   ⚠️ Error interacting: {e}")
            return False
        
        for x_path_to_close in x_paths:
            # 1. Try Main Content
            driver.switch_to.default_content()
            if try_click(driver, x_path_to_close):
                time.sleep(1)
                continue # Move to next rule

            # 2. If not found, iterate ALL iframes
            iframes = driver.find_elements(By.TAG_NAME, "iframe")
            for i, iframe in enumerate(iframes):
                try:
                    driver.switch_to.default_content() # Reset
                    driver.switch_to.frame(iframe)     # Enter iframe
                    if try_click(driver, x_path_to_close):
                        time.sleep(1)
                        break # Stop looking through iframes for this rule
                except Exception:
                    # Iframes sometimes unload or deny access, just skip
                    continue
            
            # Always reset to default after finishing a rule
            driver.switch_to.default_content()
            
            
    def save_screenshot(self, driver, url):
        if not driver:
            return None
        
        try:
            print("Taking screenshot")
            png_data = driver.get_screenshot_as_png()
        except Exception as e:
            print(f"Could not take screenshot: {e}")
            return
        
        print("Saving screenshot")
        try:            
            timestamp = int(time.time())
            filename = f"{timestamp}.png"
            file_path = os.path.join(self.screenshots_path, filename)
        
            with open(file_path, "wb") as f:
                f.write(png_data)
            print(f"📸 Screenshot saved to: {file_path}")
        except Exception as e:
            print(f"❌ Failed to write screenshot file: {e}")
        
    
    
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
            
            proxies = self.proxy_manager.get_next_proxy(url)
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
            
            source_name:str = self.extract_source_name(url)
            print(f"DEBUG: Identified source as: '{source_name}' for URL: {url}")
            
            driver = self.get_clean_driver(proxy_url, user_agent, custom_headers)
            driver.get(url)
           
            try:
                time.sleep(2)
                self.handle_scroll(driver)
                self.save_screenshot(driver,url)
                self.handle_pop_ups(source_name, driver)
                self.save_screenshot(driver,url)
                self.handle_scroll(driver)
                self.save_screenshot(driver,url)
            except Exception as e:
                data = self.collect_failure_screenshots()
                self.save_screenshot(data)
                raise Exception(f"Failed to navigate page: {e}")
            
            body_element = driver.find_element(By.TAG_NAME, "main").get_attribute("innerHTML")
            if "ERR_CERT_AUTHORITY_INVALID" in body_element:
                raise Exception("SSL Bypass failed")
            print(f"[SUCCESS] Successfully fetched {url}")
            return body_element

        except Exception as e:
            print(f"[ERROR] Fetching {url}: {e}")
            traceback.print_exc()
            raise e
        
        finally:
            if driver:
                # Use the name with the underscore
                dirs_to_clean = getattr(driver, '_thread_dirs', [])
                try:
                    driver.quit()
                    time.sleep(2) # Buffer for OS to release file locks
                    for d in dirs_to_clean:
                        if os.path.exists(d):
                            shutil.rmtree(d, ignore_errors=True)
                except Exception as cleanup_err:
                    print(f"Cleanup Error: {cleanup_err}")

script_dir: str = os.path.dirname(os.path.abspath(__file__))
combined_hints_file_path: str = os.path.abspath(os.path.join(script_dir, "../", "page_structure_hints", "combined_hints.json"))
screenshots_folder_path: str = "/app/microservices/web_scraper/screenshots"
os.makedirs(screenshots_folder_path, exist_ok=True)
fetch_manager = FetchManagerSelenium(proxy_manager=proxy_manager_paid, hint_path=combined_hints_file_path, screenshots_path = screenshots_folder_path)
