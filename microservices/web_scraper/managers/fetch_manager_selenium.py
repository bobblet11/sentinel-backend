"""Selenium-based browser automation for fetching article HTML.

This module implements the FetchManager using Selenium with anti-bot evasion:
rotating proxies, sticky user agents, country-specific headers, and undetected
ChromeDriver. Handles popup/cookie modal closing and screenshot capture.

Key Features:
    - Thread-safe singleton with per-thread driver isolation
    - Rotating proxy selection via ProxyManagerPaid with bad proxy reporting
    - Sticky user agents per proxy for consistent browser fingerprinting
    - Country-specific Accept-Language headers from proxy IP geolocation
    - Pop-up detection and automatic modal closing via XPath selectors
    - Page scrolling and dynamic content loading
    - Exponential retry with jitter for timeout resilience
    - Screenshot capture for debugging and monitoring

The public interface is fetch_article_html(url) which returns the full HTML page.
"""
import hashlib
import json
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from logging import Logger, getLogger
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from pyvirtualdisplay import Display
from requests import Request
from requests.exceptions import RequestException
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from seleniumwire import undetected_chromedriver as uc
from undetected_chromedriver import Chrome, ChromeOptions, Patcher

from common.io.screenshot_handler import RotatingScreenshotHandler
from common.requests.retry_request import exponential_retry
from common.requests.user_agent_manager import BrowserProfile, user_agent_manager
from microservices.web_scraper.config import (
    FETCH_DELAY_GROWTH_RATE,
    INITIAL_FETCH_DELAY_S,
    MAX_FETCH_RETRIES,
    MAX_SCREENSHOT_FOLDER_SIZE,
)
from microservices.web_scraper.managers.proxy_manager_paid import (
    ProxyManagerPaid,
    proxy_manager_paid,
)

ProxyRequestDict = Optional[Dict[str, str]]

CURRENT_DIR: str = Path(os.path.dirname(os.path.abspath(__file__)))
HINTS_PATH: Path = CURRENT_DIR / ".." / "page_structure_hints" / "combined_hints.json"

URL_TO_OUTLET_MAP: Dict[str, str] = {
    ("abcnews", "abcnews.go.com"): "ABC",
    ("bbc", "www.bbc.com"): "BBC",
    ("cbc", "www.cbc.ca"): "CBC",
    ("cbs", "www.cbsnews.com"): "CBS",
    ("euronews", "www.euronews.com"): "Euronews",
    ("nbcnews", "www.nbcnews.com"): "NBC",
    ("npr", "www.npr.org"): "NPR",
    ("theguardian", "www.theguardian.com"): "The_Guardian",
}
LONG_DELAY_S: int = 6
MEDIUM_DELAY_S: int = 4
SHORT_DELAY_S: int = 2
MAX_NUMBER_SCROLLS: int = 5
PAGE_LOAD_TIMEOUT_S: int = 300
SCRIPT_LOAD_TIMEOUT_S: int = 300


@dataclass(frozen=True)
class DriverConfig:
    proxy_url: str
    browser_profile: BrowserProfile
    headers: Dict[str, str]

    source_name: str
    country_code: str
    lang_str: str

    @property
    def get_config_summary_string(self):
        source_name_row: str = f"\n\tsource: {self.source_name}"
        proxy_url_row: str = f"\n\tproxy_url: {self.proxy_url}"
        proxy_country_code_row: str = f"\n\tproxy_country_code: {self.country_code}"
        user_agent_row: str = f"\n\tuser_agent: {self.browser_profile}"
        lang_str_row: str = f"\n\tlang_string: {self.lang_str}"
        return (
            source_name_row
            + proxy_url_row
            + proxy_country_code_row
            + user_agent_row
            + lang_str_row
        )


class FetchManagerSelenium:
    """Thread-safe singleton for Selenium-based article HTML fetching.

    Manages browser driver pool with per-thread isolation. Coordinates proxy
    rotation, sticky user agents, pop-up handling, and retry logic with
    exponential backoff and proxy health tracking.

    Attributes:
        proxy_manager: ProxyManagerPaid instance for rotating proxy selection.
        default_timeout: (connect_timeout, read_timeout) tuple in seconds.
        display: Virtual X11 display for headless browser execution.
        base_driver_path: Path to master chromedriver binary.
        hint_config: JSON config for pop-up XPath selectors per outlet.
        x_path_config: Pre-compiled XPath dictionary for each news source.
    """

    _instance = None
    _class_lock = threading.Lock()
    _init_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._class_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
        self,
        default_timeout: Tuple[float, float] = (15.0, 20.0),
        proxy_manager: ProxyManagerPaid = None,
        hint_path: Path = CURRENT_DIR / "combined_hints.json",
        screenshot_handler: RotatingScreenshotHandler = RotatingScreenshotHandler(),
    ):
        """Initialize browser automation environment, download driver, start display.

        Detects Chrome/Chromium binary, downloads/patches matching chromedriver,
        starts virtual X11 display, and initializes proxy and hint configs.
        Raises SystemExit if proxy_manager is missing or browser binary not found.

        Args:
            default_timeout: (connect_s, read_s) tuple for Selenium waits.
            proxy_manager: ProxyManagerPaid instance (required).
            hint_path: Path to JSON config with pop-up XPath selectors.
            screenshot_handler: RotatingScreenshotHandler for capture storage.

        Raises:
            SystemExit: If proxy_manager missing or Chrome binary not found.
            FileNotFoundError: If Chrome/Chromium not installed.
        """
        if getattr(self, "_initialized", False):
            return

        with self._init_lock:
            if getattr(self, "_initialized", False):
                return

            self.logger: Logger = getLogger("fetch_manager_SELENIUM")
            self.logger.info("Starting initialisation")

        if not proxy_manager:
            self.logger.error("No proxy manager available!")
            exit(1)

        self._create_selenium_wire_CA_folder()
        hint_path.parent.mkdir(parents=True, exist_ok=True)

        self.proxy_manager: ProxyManagerPaid = proxy_manager
        self.default_timeout: Tuple[float, float] = default_timeout
        self.hint_config: Dict[str, Dict[str, Any]] = json.loads(hint_path.read_text())
        self.x_path_config: Dict[str, List[str]] = self._generate_xpath_dict(
            self.hint_config
        )
        self.screenshot_handler: RotatingScreenshotHandler = screenshot_handler

        # Start Global Virtual Display
        self.logger.info("Starting Global Virtual Display...")
        self.display = Display(visible=0, size=(1920, 1080))
        self.display.start()

        # We download/patch the driver ONCE here, then copy it for threads later.
        self.logger.info("Detecting Chrome/Chromium version and preparing driver...")
        try:
            # 1. Find installed Chrome/Chromium binary
            browser_candidates = [
                "google-chrome",
                "chromium",
                "chromium-browser",
                "/usr/bin/google-chrome",
                "/usr/bin/chromium",
                "/usr/bin/chromium-browser",
            ]
            browser_binary = None
            for candidate in browser_candidates:
                resolved = shutil.which(candidate) or (
                    candidate if os.path.exists(candidate) else None
                )
                if resolved:
                    browser_binary = resolved
                    break

            if not browser_binary:
                raise FileNotFoundError(
                    "No Chrome/Chromium binary found. Expected one of: google-chrome, chromium."
                )

            self.chrome_binary_path = browser_binary
            browser_name = os.path.basename(browser_binary)
            is_chromium = "chromium" in browser_name

            # 2. Get installed browser version
            result = subprocess.run(
                [browser_binary, "--version"], capture_output=True, text=True
            )
            version_output = result.stdout.strip().split()[-1]
            major_version = int(version_output.split(".")[0])
            self.logger.info(
                f"Detected Browser Version: {version_output} (Major: {major_version}) using {browser_binary}"
            )
            user_agent_manager.set_max_browser_version(major_version)

            # 3. Prefer system chromedriver when using Chromium (arm64)
            system_chromedriver = shutil.which("chromedriver")
            if is_chromium and system_chromedriver:
                self.base_driver_path = system_chromedriver
                os.chmod(self.base_driver_path, 0o755)
                self.logger.info(
                    f"Using system chromedriver at: {self.base_driver_path}"
                )
            else:
                # Download matching driver for Google Chrome
                patcher = Patcher(version_main=major_version)
                patcher.auto()
                self.base_driver_path = patcher.executable_path
                os.chmod(self.base_driver_path, 0o755)
                self.logger.info(f"Master driver ready at: {self.base_driver_path}")

        except Exception as e:
            self.logger.error(f"Failed to prepare driver: {e}")
            raise e

        self._initialized: bool = True
        self.logger.info("Initialisation complete!")

    def _create_selenium_wire_CA_folder(self) -> None:
        """Pre-create the selenium-wire CA folder to prevent the 'PEM routines' error"""
        os.makedirs(os.path.expanduser("~/.seleniumwire"), exist_ok=True)

    @staticmethod
    def get_accept_language_string(country_code: str = "US") -> str:
        language_options: Dict[str, str] = {
            "CA": "en-CA,en;q=0.9,fr-CA;q=0.8",
            "GB": "en-GB,en;q=0.9",
            "US": "en-US,en;q=0.9",
            "FR": "en-US,en;q=0.9,fr-FR;q=0.8,fr;q=0.7",
        }
        default_language_string: str = language_options["US"]
        return language_options.get(country_code.upper(), default_language_string)

    @staticmethod
    def find_free_port() -> int:
        """Finds a truly free port for the selenium-wire proxy to bind to."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            s.listen(1)
            port: int = s.getsockname()[1]
        return port

    def _create_enhanced_headers(
        self, accept_language: str = "en-US,en;q=0.9"
    ) -> Dict[str, str]:
        """Returns a dictionary of headers to better mimic a real browser."""
        return {
            "Referer": "https://www.google.com/",
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

    def _generate_interceptor_function(
        self, custom_headers: Dict[str, str]
    ) -> Callable:

        def interceptor(request: Request):
            """Intercepts request made by Selenium and replaces headers. Returns a dictionary of headers to better mimic a real browser."""
            if request.headers.get("Sec-Fetch-Dest") == "document":
                for key, value in custom_headers.items():
                    if key in request.headers:
                        del request.headers[key]
                    request.headers[key] = value

        return interceptor

    def _generate_new_driver(self, config: DriverConfig) -> Chrome:
        # Ports
        wire_port: int = self.find_free_port()
        debug_port: int = self.find_free_port()

        # Unique Paths per Thread
        unique_id = uuid.uuid4().hex[:8]
        driver_bin_dir: str = tempfile.mkdtemp(prefix=f"uc_driver_{unique_id}_")
        user_data_dir: str = tempfile.mkdtemp(prefix=f"chrome_prof_{unique_id}_")
        wire_tmp_dir: str = tempfile.mkdtemp(prefix=f"wire_{unique_id}_")

        # Copy Driver Binary
        # Copy the master driver to this thread's private folder to prevent race conditions
        thread_driver_path = os.path.join(driver_bin_dir, "chromedriver")
        shutil.copy(self.base_driver_path, thread_driver_path)
        os.chmod(thread_driver_path, 0o755)

        options: ChromeOptions = uc.ChromeOptions()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-setuid-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-infobars")
        options.add_argument("--disable-extensions")
        options.add_argument("--remote-allow-origins=*")

        options.add_argument("--window-size=1920,1080")
        options.add_argument("--start-maximized")
        options.add_argument("--ignore-certificate-errors")

        options.add_argument(f"--remote-debugging-port={debug_port}")
        options.add_argument(f"--user-data-dir={user_data_dir}")
        options.add_argument(f"--user-agent={config.browser_profile.user_agent_string}")
        options.add_argument(
            f"--window-size={config.browser_profile.screen_width},{config.browser_profile.screen_height}"
        )
        options.binary_location = getattr(
            self, "chrome_binary_path", "/usr/bin/google-chrome"
        )

        proxy_options: Dict[str, Any] = {
            "proxy": {"http": config.proxy_url, "https": config.proxy_url},
            "port": wire_port,
            "request_storage_base_dir": wire_tmp_dir,
            "request_storage": "memory",
            "verify_ssl": False,
        }

        try:
            driver: Chrome = uc.Chrome(
                options=options,
                seleniumwire_options=proxy_options,
                headless=False,
                version_main=None,
                use_subprocess=True,
                driver_executable_path=thread_driver_path,
            )

            driver.execute_cdp_cmd(
                "Network.setUserAgentOverride",
                {
                    "userAgent": config.browser_profile.user_agent_string,
                    "platform": config.browser_profile.os_platform,
                    "userAgentMetadata": config.browser_profile.cdp_metadata,
                },
            )

            driver.execute_cdp_cmd(
                "Page.addScriptToEvaluateOnNewDocument",
                {"source": f"""
                    Object.defineProperty(navigator, 'hardwareConcurrency', {{
                        get: () => {config.browser_profile.cpu_concurrency}
                    }});
                    Object.defineProperty(navigator, 'deviceMemory', {{
                        get: () => {config.browser_profile.device_memory}
                    }});
                    Object.defineProperty(navigator, 'platform', {{
                        get: () => '{config.browser_profile.os_platform}'
                    }});
                """},
            )

        except Exception as e:
            if hasattr(e, "msg"):
                self.logger.error(f"Chrome Start Error: {e.msg}")
            raise e

        # Add cleanup paths for this specific thread
        driver._thread_dirs = [user_data_dir, wire_tmp_dir, driver_bin_dir]
        driver.request_interceptor = self._generate_interceptor_function(config.headers)
        return driver

    def _extract_source_name(
        self, article_url: str, default_source_name: str = "BBC"
    ) -> str:
        for url_patterns, source_name in URL_TO_OUTLET_MAP.items():
            for pattern in url_patterns:
                if pattern in article_url:
                    return source_name

        return default_source_name

    def _create_xpath(self, rule_name: str, rule_data: Dict[str, Any]) -> str:
        """
        Converts the JSON rule into a valid XPath string.
        """
        xpath_parts: List[str] = []

        # 1. Handle Parents (Ancestors)
        if "parents" in rule_data:
            for parent in reversed(rule_data["parents"]):
                tag: str = parent.get("tag", "*")
                attrs: str = self._create_attribute_predicates(parent)
                xpath_parts.append(f"//{tag}{attrs}")

        # 2. Handle the Target Element (Button we want to close)
        tag: str = rule_data.get("tag", "*")
        attrs: str = self._create_attribute_predicates(rule_data)
        xpath_parts.append(f"//{tag}{attrs}")

        self.logger.debug(f"Xpath for {rule_name} = {xpath_parts}")
        return "".join(xpath_parts)

    def _create_attribute_predicates(self, tag_description: Dict[str, Any]) -> str:
        """
        Helper to turn a dictionary {"class": "foo", "id": "bar"}
        into XPath attribute string "[contains(@class, 'foo') and @id='bar']"
        """
        predicates: List[str] = []

        ignore_keys: List[str] = ["tag", "parents"]

        for key, value in tag_description.items():
            if key in ignore_keys:
                continue

            if key == "class":
                predicates.append(f"contains(@class, '{value}')")
            elif key == "text_contains":
                predicates.append(f"contains(., '{value}')")
            else:
                predicates.append(f"@{key}='{value}'")

        if not predicates:
            return ""

        return "[" + " and ".join(predicates) + "]"

    def _handle_scroll(self, driver: Chrome) -> None:
        self.logger.debug("Scrolling down...")
        wait = WebDriverWait(driver, 5)

        last_height: int = driver.execute_script("return document.body.scrollHeight")

        for _ in range(MAX_NUMBER_SCROLLS):
            driver.execute_script("window.scrollBy(0, 800);")

            try:
                wait.until(
                    lambda d: d.execute_script("return document.body.scrollHeight")
                    > last_height
                )

                last_height = driver.execute_script("return document.body.scrollHeight")
                self.logger.debug(f"Page height increased to {last_height}px.")

            except TimeoutException:
                self.logger.debug("Page height did not change. Reached the bottom!")
                break

        self.logger.debug("Reached the bottom!")

    def _generate_xpath_dict(
        self, hint_config: Dict[str, Dict[str, Any]]
    ) -> Dict[str, List[str]]:
        """
        Generates a map of all the close buttons needed to be pressed for each source.
        """
        self.logger.info("Generating XPATH dictionary...")

        xpath_dict: Dict[str, List[str]] = {}
        for source_name, source_rules in hint_config.items():
            xpath_dict[source_name] = []

            if not source_rules.get("selectors", None):
                continue

            for rule_name, rule_data in source_rules.get("selectors").items():
                self.logger.debug(rule_name, rule_data)

                xpath: str = self._create_xpath(rule_name, rule_data)
                xpath_dict[source_name].append(xpath)

        return xpath_dict

    def _handle_pop_ups(self, source_name: str, driver: Chrome) -> None:
        """Detect and close pop-ups/modals using XPath selectors from hint config.

        Attempts to locate and click close buttons for each outlet. Falls back to
        searching within iframes if main content fails. All clicks raise failure
        stream routing but do not stop processing.

        Args:
            source_name: Outlet name to look up XPath rules.
            driver: Selenium Chrome driver instance.
        """
        x_paths_for_buttons: List[str] = self.x_path_config.get(source_name, [])

        if not x_paths_for_buttons:
            self.logger.warning(f"No xpath rules found for {source_name}")
            return

        waiter = WebDriverWait(driver, timeout=2)

        def click_xpath(
            context_driver: Chrome, xpath: str, waiter: WebDriverWait
        ) -> bool:
            self.logger.debug(f"Trying to click {xpath}")
            try:
                element = waiter.until(
                    EC.presence_of_element_located((By.XPATH, xpath))
                )

                if element.is_displayed():
                    self.logger.info(f"Found popup [{xpath}]. Clicking...")

                    try:
                        element.click()
                    except ElementClickInterceptedException:
                        context_driver.execute_script("arguments[0].click();", element)

                    self.logger.info(f"✅ Closed [{xpath}]")

                    return True

            except TimeoutException:
                self.logger.warning("Timeout: Pop up did not appear.")
            except Exception as e:
                self.logger.error(f"⚠️ Error interacting: {e}")
            return False

        for button_to_close in x_paths_for_buttons:

            driver.switch_to.default_content()

            # Successfully clicked a button
            if click_xpath(driver, button_to_close, waiter):
                continue

            # If not found, iterate ALL iframes
            iframes = driver.find_elements(By.TAG_NAME, "iframe")
            for i, iframe in enumerate(iframes):
                try:
                    driver.switch_to.default_content()
                    driver.switch_to.frame(iframe)
                    if click_xpath(driver, button_to_close, waiter):
                        break
                except Exception:
                    # Iframes sometimes unload or deny access, just skip
                    continue

            # Always reset to default after finishing a rule
            driver.switch_to.default_content()

    def _take_and_save_screenshot(
        self, driver: Chrome, article_url: str, prefix: str = ""
    ) -> None:
        if not driver:
            return None

        try:
            self.logger.debug("Taking screenshot")
            png_data: bytes = driver.get_screenshot_as_png()
        except Exception as e:
            self.logger.error(f"Could not take screenshot: {e}")
            return

        try:
            self.logger.debug("Saving screenshot")

            timestamp: int = int(time.time())
            url_hash: str = hashlib.md5(article_url.encode("utf-8")).hexdigest()[:8]
            filename: str = f"{prefix}_{timestamp}_{url_hash}.png"
            self.screenshot_handler.save_screenshot(png_data, filename=filename)
            capacity: float = (
                self.screenshot_handler.current_bytes
                / self.screenshot_handler.max_bytes
                if self.screenshot_handler.max_bytes != 0
                else 100.0
            )
            self.logger.info(
                f"📸 Screenshot saved as: {filename} to {self.screenshot_handler.screenshot_directory} ({capacity}% used)"
            )
        except Exception as e:
            self.logger.error(f"Could not save screenshot: {e}")
            return

    def _create_driver_config(self, article_url: str) -> DriverConfig:
        """Build driver configuration: proxy, user agent, headers, outlet name.

        Selects rotating proxy via proxy_manager, looks up country code from proxy IP,
        gets sticky user agent for that proxy, and creates country-specific headers.

        Args:
            article_url: URL to identify outlet and select proxy.

        Returns:
            DriverConfig with proxy_url, browser_profile, headers, and locale info.

        Raises:
            Exception: If proxy_url not found in proxy dict.
        """
        self.logger.debug(
            f"Identified source as: '{source_name}' for URL: {article_url}"
        )

        proxies: ProxyRequestDict = self.proxy_manager.get_next_proxy(article_url)
        proxy_url: str = proxies.get("https", proxies.get("http"))
        if not proxy_url:
            raise Exception("Proxy dictionary found, but no http/https URL present")

        ip_country_mapping: Dict[str, str] = getattr(
            self.proxy_manager, "ip_country_mapping", {}
        )
        if ip_country_mapping is None:
            self.logger.warning(
                "IP Country Map was not generated. Proxy source was not initialised correctly"
            )
        proxy_country_code: str = ip_country_mapping.get(proxy_url, "US")
        lang_string: str = self.get_accept_language_string(proxy_country_code)

        headers: Dict[str, str] = self._create_enhanced_headers(lang_string)
        browser_profile: BrowserProfile = user_agent_manager.get_sticky_browser_profile(
            proxy_url
        )

        driver_config: DriverConfig = DriverConfig(
            proxy_url,
            browser_profile,
            headers,
            source_name,
            proxy_country_code,
            lang_string,
        )
        self.logger.debug(
            f"Created driver config for {article_url}"
            + driver_config.get_config_summary_string
        )
        return driver_config

    def _scroll_and_close_popups(
        self, driver: Chrome, article_url: str, source_name: str
    ) -> None:
        """Scroll page, handle pop-ups/modals, and capture screenshots for debugging.

        Scrolls to bottom (lazy loads content), closes detected pop-ups via XPath,
        and takes screenshots before/after for failure analysis.

        Args:
            driver: Selenium Chrome driver instance.
            article_url: URL being fetched (for screenshot naming).
            source_name: Outlet name to select appropriate pop-up rules.

        Raises:
            Exception: If scroll/pop-up handling fails (raised as generic exception).
        """
        self.logger.debug("Attempting to execute scroll and close commands in page")
        try:
            self._handle_scroll(driver)
            self._take_and_save_screenshot(driver, article_url)
            self._handle_pop_ups(source_name, driver)
            self._take_and_save_screenshot(driver, article_url)
            self._handle_scroll(driver)
            self._take_and_save_screenshot(driver, article_url)

        except Exception as e:
            self._take_and_save_screenshot(driver, article_url, prefix="FAIL")
            raise Exception(f"Failed to navigate page: {e}")

    def _extract_html(self, driver: Chrome) -> str:
        # Use page_source to ensure <head> and <meta> tags are captured
        full_html: str = driver.page_source

        if not full_html or len(full_html) < 200:
            self.logger.warning("Captured page_source was empty or too short.")
            raise Exception("Page source extraction failed or empty")

        if "ERR_CERT_AUTHORITY_INVALID" in full_html:
            raise Exception("SSL Bypass failed")

        return full_html

    def _clean_up_driver(self, driver: Chrome) -> None:
        try:
            driver.quit()
        except Exception:
            pass

        # Clean up temporary directories
        try:
            dirs_to_clean: List[str] = getattr(driver, "_thread_dirs", [])
            for directory in dirs_to_clean:
                if os.path.exists(directory):
                    shutil.rmtree(directory, ignore_errors=True)
        except Exception as cleanup_err:
            self.logger.warning(f"Failed to clean dirs: {cleanup_err}")

    @exponential_retry(
        max_attempts=MAX_FETCH_RETRIES,
        initial_delay_s=INITIAL_FETCH_DELAY_S,
        growth_rate=FETCH_DELAY_GROWTH_RATE,
        jitter=True,
        on_exceptions=(RequestException, WebDriverException, Exception),
    )
    def fetch_article_html(self, article_url: str) -> str:
        """Fetch full HTML from article URL using rotating proxies and browser automation.

        Selects rotating proxy and sticky user agent, launches undetected ChromeDriver,
        scrolls page, closes pop-ups, and extracts HTML. On failure, reports proxy
        as bad via proxy_manager. Wrapped by exponential retry decorator for resilience.

        Args:
            article_url: URL of article to fetch.

        Returns:
            Full HTML page source as string (page_source).

        Raises:
            TimeoutException: Page load exceeded timeout; proxy likely bad.
            WebDriverException: Selenium/browser error; proxy likely bad.
            Exception: Other errors (SSL, rendering failures).
        """
        driver: Chrome = None
        driver_config: DriverConfig = None

        try:
            self.logger.debug(f"Fetching HTML for {article_url}")
            driver_config: DriverConfig = self._create_driver_config(article_url)
            driver: Chrome = self._generate_new_driver(driver_config)

            driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT_S)
            driver.set_script_timeout(SCRIPT_LOAD_TIMEOUT_S)

            driver.get(article_url)

            self._scroll_and_close_popups(
                driver, article_url, driver_config.source_name
            )

            body_element: str = self._extract_html(driver)
            self.logger.debug(
                f"[SUCCESS] Successfully fetched {len(body_element)} bytes from {article_url}"
            )
            return body_element

        except TimeoutException as e:
            self.logger.error(
                f"[ERROR] TIMEOUT: Potential proxy error on {article_url}: {e}"
            )
            self.proxy_manager.report_bad_proxy(driver_config.proxy_url)
        except WebDriverException as e:
            self.logger.error(
                f"[ERROR] SELENIUM FAIL: Potential proxy error on {article_url}: {e}"
            )
            self.proxy_manager.report_bad_proxy(driver_config.proxy_url)
        except Exception as e:
            self.logger.error(f"[ERROR] OTHER: Could not fetch {article_url}: {e}")
            self.proxy_manager.report_bad_proxy(driver_config.proxy_url)
            raise e

        finally:
            if driver:
                self._clean_up_driver(driver)


fetch_manager = FetchManagerSelenium(
    proxy_manager=proxy_manager_paid,
    hint_path=HINTS_PATH,
    screenshot_handler=RotatingScreenshotHandler(max_bytes=MAX_SCREENSHOT_FOLDER_SIZE),
)
