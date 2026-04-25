# nyt_scraper.py
import re
from typing import Optional

from bs4 import BeautifulSoup

from microservices.web_scraper.parsers.base_parser import BaseParser, ParseResult


class CBCParser(BaseParser):
    def extract(self, soup: BeautifulSoup, article_url: str) -> Optional[ParseResult]:
        container = soup.find("main") or soup.find("div", {"id": "app"}) or soup
        self._remove_unwanted(container)

        paragraphs = container.find_all("p")
        text = self._clean_paragraphs(paragraphs)
        if not text:
            return None

        # Title
        title = None
        og = soup.find("meta", property="og:title")
        if og and og.get("content"):
            title = og["content"].strip()
        if not title:
            h1 = (
                soup.find("h1", class_="detailHeadline")
                or soup.find("h1", class_="sclt-story-headline")
                or soup.find("h1")
            )
            if h1:
                title = h1.get_text(strip=True)
        if not title and soup.title:
            title = soup.title.string

            # Author & Date
        author = None
        published_at = None

        time_tag = soup.find("time")
        if time_tag:
            published_at = time_tag.get("datetime")

        # DOM
        if not author or not published_at:
            byline_div = (
                soup.find("div", class_="byline")
                or soup.find("div", class_="bylineDetails")
                or soup.find("div", class_="story-credits")
            )

            if byline_div:
                # Author
                if not author:
                    # Try all <a> links first, fallback to text
                    links = byline_div.find_all("a")
                    if links:
                        author = ", ".join(
                            [
                                a.get_text(strip=True)
                                for a in links
                                if a.get_text(strip=True)
                            ]
                        )
                    else:
                        author_text = byline_div.get_text(" ", strip=True)

                        # remove 'By' prefix
                        if author_text.lower().startswith("by "):
                            author_text = author_text[3:].strip()

                        # remove everything after separator like "·"
                        if "·" in author_text:
                            author_text = author_text.split("·")[0].strip()

                        # remove "Posted:" or similar noise
                        author_text = re.sub(r"Posted:.*", "", author_text).strip()

                        if author_text:
                            # remove "Posted..." part if present
                            author_text = re.split(r"·|Posted:", author_text)[0].strip()

                            # remove leading "By"
                            author_text = re.sub(
                                r"^By\s+", "", author_text, flags=re.IGNORECASE
                            )

                            author = author_text if author_text else None

                # Date Fallback
                if not published_at:
                    # Try <time datetime=""> first
                    time_tag = byline_div.find("time")
                    if time_tag and time_tag.get("datetime"):
                        published_at = time_tag["datetime"]
                    else:
                        # regex fallback
                        full_text = byline_div.get_text(" ", strip=True)
                        date_pattern = r"(\w+ \d{1,2}, \d{4})"  # e.g., March 30, 2026
                        match = re.search(date_pattern, full_text)
                        if match:
                            published_at = match.group(1)
        if not title or not author or not published_at:
            print(
                f"[HARDCODED PARSE ERROR] something is not correct for {article_url}\n\t:text{text}\n\ttitle:{title}\n\tauthor:{author}\n\tpublished:{published_at}"
            )

        return ParseResult(text, title, author, published_at)
