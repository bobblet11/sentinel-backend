# nyt_scraper.py
import re
from typing import Dict, Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from microservices.web_scraper.parsers.base_parser import BaseParser, ParseResult
class TheGuardianParser(BaseParser):
    def extract(self, soup: BeautifulSoup, article_url: str) -> Optional[ParseResult]:
        # Guardian usually puts content in div[data-gu-name='body'] or main
        container = (
            soup.find("div", {"data-gu-name": "body"}) or
            soup.find("article") or
            soup.find("main") or
            soup
        )
        self._remove_unwanted(container)

        paragraphs = container.find_all("p")
        # also look inside divs if no paragraphs found
        if not paragraphs:
            paragraphs = container.find_all("div")
        text = self._clean_paragraphs(paragraphs)
        if not text:
            return None

        # Title
        title = None
        og = soup.find("meta", property="og:title")
        if og and og.get("content"):
            title = og["content"].strip()
        if not title:
            h1 = soup.find("h1")
            if h1:
                title = h1.get_text(strip=True)
        if not title and soup.title:
            title = soup.title.string  
        
        # Author & Date
        author = None
        published_at = None
        
        
        meta_author = soup.find("meta", {"name": "author"}) or soup.find("meta", {"property": "article:author"})
        if meta_author and meta_author.get("content"):
            content = meta_author["content"]
            if content.startswith("http"):
                slug = content.split("/")[-1]
                author = " ".join(word.capitalize() for word in slug.split("-"))

            else:
                author = content

        # if meta_author and meta_author.get("content"):
        #     author = meta_author["content"]

        meta_date = soup.find("meta", {"property": "article:published_time"})
        if meta_date and meta_date.get("content"):
            published_at = meta_date["content"]

        # DOM Fallback
        if not author:
            # Typo fixed: address, not addresss
            address_tag = soup.find("address") or soup.find("div", class_="byline")
            if address_tag:
                links = address_tag.find_all("a")
                if links:
                    author = ", ".join([a.get_text(strip=True) for a in links])
                else:
                    author = address_tag.get_text(strip=True)

        if not published_at:
            # Fallback to <time> tag if meta missing
            time_tag = soup.find("time")
            if time_tag:
                published_at = time_tag.get("datetime") or time_tag.get_text(strip=True)

        if not title or not author or not published_at:
            print(f"[HARDCODED PARSE ERROR] something is not correct for {article_url}\n\t:text{text}\n\ttitle:{title}\n\tauthor:{author}\n\tpublished:{published_at}") 

        return ParseResult(text, title, author, published_at)
