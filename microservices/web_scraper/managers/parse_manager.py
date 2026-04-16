#parsing_manager.py
import json
from logging import Logger, getLogger
import re
from unittest import result
import trafilatura
import threading 

from typing import Any, Dict, List, Optional, Callable
from bs4 import BeautifulSoup
from microservices.web_scraper.managers.parser_registry_manager import ParserRegistryManager
from microservices.web_scraper.parsers.base_parser import BaseParser
from dataclasses import asdict, dataclass
from datetime import datetime

@dataclass
class ParseResult:
    text: str
    title: Optional[str]
    author: Optional[str]
    published_at: Optional[str]
    
    def __getitem__(self, key):
        return getattr(self, key, None)
    
    def __setitem__(self, key, value):
        if hasattr(self, key):
            setattr(self, key, value)
        else:
            raise KeyError(f"{key} is not a valid field")
        

class ParseManager:
    """
    Robust raw_HTML -> article parser which:
      1) Checks hardcoded scrapers (registry)
      2) Uses RSS metadata if provided (message-driven)
      3) Uses trafilatura
      4) Falls back to DOM paragraph extraction
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
    
    
    def __init__(self, registry: ParserRegistryManager = None):
        if getattr(self, "_initialized", False):
            return

        with self._init_lock:
            if getattr(self, "_initialized", False):
                return
            
            self.logger:Logger = getLogger("parse_manager")
            self.logger.info(f"Starting initialisation")
        
            self.hardcoded_parser_registry = registry or ParserRegistryManager()
            
            self._initialized = True
            self.logger.info(f"Initialisation complete!")
        
    def _attempt_multiple_keys(self, payload:Dict[str,Any], keys: List[str]) -> Optional[Any]:
        """
        Finds a key inside of a dictionary
        """
        if not keys or not payload:
            raise Exception("Missing arguments")
            
        for key in keys:
            if key in payload:
                return payload[key]
        
        return None
    
    def _strategy_metadata(self, article_metadata: Dict[str,str])  -> Optional[ParseResult]:
        self.logger.debug(f"[level 0] Attempting to parse with metadata")
        
        if not article_metadata:
            return None
        
        title:str = self._attempt_multiple_keys(article_metadata, ["title"])
        text:str = self._attempt_multiple_keys(article_metadata, ["content", "description"])
        author:str = self._attempt_multiple_keys(article_metadata, ["author", "creator"])
        published_at:str = self._attempt_multiple_keys(article_metadata, ["published", "pubDate"])
        
        return ParseResult(
            text,
            title,
            author,
            published_at
        )


    def _strategy_hardcoded(self, article_url:str, soup:BeautifulSoup)  -> Optional[ParseResult]:
        self.logger.debug(f"[level 1] Attempting parsing with hardcoded parser")
        
        if not article_url:
            return None
        
        hardcoded_parser: Optional[BaseParser] = self.hardcoded_parser_registry.find_matching_parser(article_url)
        
        if not hardcoded_parser:
            return None

        result: Optional[ParseResult]= hardcoded_parser.extract(soup, article_url)
        return result
    
    
    def _strategy_trafilatura(self, raw_html:str)  -> Optional[ParseResult]:
        self.logger.debug(f"[level 2] Attempting parsing with trafilatura")
        
        metadata = trafilatura.extract_metadata(raw_html)

        dirty_text: Optional[str] = self._extract_text_with_trafilatura(raw_html)
        
        if not dirty_text:
            return None
        
        clean_text: Optional[str]  = self._clean_text(dirty_text)
        
        if not clean_text:
            return None
        
        author = metadata.author if metadata else None
        published_at = metadata.date if metadata else None
        return ParseResult(clean_text, None, author, published_at)
    
    
    def _strategy_fallback(self, soup: BeautifulSoup) -> Optional[ParseResult]:
        self.logger.debug(f"[level 3] Attempting parsing with fallback")
        text:str = self._fallback_extract_text(soup)
        
        return ParseResult(text, None, None, None)
    
    def _is_sufficient(self, result: ParseResult) -> bool:
        return (
            result
            and result.text
            and len(result.text.strip()) > 200
        )
    
    def _normalise_date(self, raw: str) -> Optional[str]:
        if not raw:
            return None
        # Already ISO with T
        if "T" in raw:
            return raw
        # Handle "2026-03-27 21:24:16 +01:00" format
        try:
            dt = datetime.fromisoformat(raw)
            return dt.isoformat()
        except Exception:
            pass
        return raw
    
    def _hydrate_missing_fields(self, result:ParseResult, soup:BeautifulSoup) -> ParseResult:
        if not result.title:
            result.title = self._extract_title(soup)
            
        if result.author:
            result.author = re.sub(r"^By\s+", "", result.author, flags=re.I).strip()
        else:
            result.author = self._extract_author(soup)
            
        if not result.published_at:
            result.published_at = self._extract_date(soup)
        
        if result.published_at:
            result.published_at = self._normalise_date(result.published_at)
            
        return result
    
    
    
    def parse_article_raw_html(self, 
        raw_html: str,
        article_url: Optional[str] = None,
        article_metadata: Optional[Dict[str, Any]] = None) -> ParseResult:
        
        if not raw_html or len(raw_html) < 20:
            raise ValueError("raw_html content too short or empty during parsing")

        
        soup = BeautifulSoup(raw_html, "lxml")
        
        strategies: List[Callable] = [
            lambda: self._strategy_hardcoded(article_url, soup),
            lambda: self._strategy_trafilatura(raw_html),
            lambda: self._strategy_metadata(article_metadata),
            lambda: self._strategy_fallback(soup)
        ]
        
        for strategy in strategies:
            result: ParseResult = strategy()
            
            if result:
                self.logger.debug(f"Strategy {strategy.__name__} returned result")

            if result and self._is_sufficient(result):
                self.logger.debug(f"Using strategy: {strategy.__name__}")
                self._hydrate_missing_fields(result, soup) 
                return result
                
        fallback_result: ParseResult = self._strategy_fallback(soup)
        self._hydrate_missing_fields(fallback_result, soup)
        return fallback_result

    def _extract_text_with_trafilatura(self, raw_html: str) -> Optional[str]:
        """
            Will rely on trafilatura to extract all text.
        """
        text: Optional[str] = trafilatura.extract(
                filecontent=raw_html, include_comments=False, include_tables=False
            )
        return text


    def _fallback_extract_text(self, soup:BeautifulSoup) -> str:
        """
            Will manually remove tags that don't contain text content.
        """
        container = soup.find(["article", "main", "body"]) or soup
        noisy_tags_to_remove: List[str] = container(
            [
                "script",
                "style",
                "noscript",
                "header",
                "footer",
                "svg",
                "meta",
                "aside",
                "nav",
                "iframe",
                "figure",
            ]
        )

        for tag in noisy_tags_to_remove:
            try:
                tag.decompose()
            except Exception:
                pass

        paragraphs: List[str] = [
            p.get_text(strip=True)
            for p in container.find_all("p")
            if p.get_text(strip=True)
        ]

        joined_paragraphs:str = "\n\n".join(paragraphs)
        return joined_paragraphs


    def _extract_title(self, soup: BeautifulSoup) -> Optional[str]:
        if soup.title and soup.title.string:
            return soup.title.string.strip()

        og = soup.find("meta", property="og:title")
        if og and og.get("content"):
            return og["content"].strip()

        # JSON-LD
        jsonld_title = self._extract_jsonld_property("headline", soup)
        if jsonld_title:
            return jsonld_title.strip()

        h1 = soup.find("h1")
        if h1:
            return h1.get_text(strip=True)

        return None

    def _extract_author(self, soup: BeautifulSoup) -> Optional[str]:
        patterns = [
            {"name": "meta", "attrs": {"name": "author"}},
            {"name": "meta", "attrs": {"property": "article:author"}},
            {"name": "meta", "attrs": {"property": "og:author"}},
        ]

        for pattern in patterns:
            tag = soup.find(pattern["name"], pattern["attrs"])
            if tag and tag.get("content"):
                content = tag["content"].strip()
                if content and not re.match(r"^https?://", content, re.I):
                    return content

        jsonld_author = self._extract_jsonld_property("author", soup)
        if jsonld_author:
            if isinstance(jsonld_author, dict):
                name = jsonld_author.get("name")
                if name and not re.match(r"^https?://", name, re.I):
                    return name
            elif isinstance(jsonld_author, str) and not re.match(r"^https?://", jsonld_author, re.I):
                return jsonld_author

        byline = soup.find(class_=re.compile(r"(author|byline)", re.I))
        if byline:
            text = byline.get_text(" ", strip=True)
            if text and not re.match(r"^https?://", text, re.I):
                return text

        return None

    def _extract_date(self, soup:BeautifulSoup) -> Optional[str]:
        date_tags = [
            {"property": "article:published_time"},
            {"name": "pubdate"},
            {"name": "publishdate"},
            {"name": "timestamp"},
            {"property": "og:updated_time"},
        ]
        for attrs in date_tags:
            tag = soup.find("meta", attrs=attrs)
            if tag and tag.get("content"):
                return tag["content"]

        jsonld_date = (
            self._extract_jsonld_property("datePublished", soup)
            or self._extract_jsonld_property("dateCreated", soup)
        )
        if jsonld_date:
            return jsonld_date

        return None

    def _extract_jsonld_property(self, prop: str, soup:BeautifulSoup) -> Optional[str]:
        scripts = soup.find_all("script", type="application/ld+json")

        for script in scripts:
            if not script.string:
                continue
        
            try:
                data = json.loads(script.string)
                if isinstance(data, list):
                    for item in data:
                        if prop in item:
                            return item[prop]
                elif isinstance(data, dict) and prop in data:
                    return data[prop]
            except Exception:
                continue
        return None

    def _clean_text(self, text: str) -> Optional[str]:
        if not text:
            return None
        text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
        return text.strip()

parse_manager = ParseManager()
