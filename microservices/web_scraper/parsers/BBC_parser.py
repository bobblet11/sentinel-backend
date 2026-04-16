# BBC_parser.py
import json
import re
from typing import Optional

from bs4 import BeautifulSoup
from microservices.web_scraper.parsers.base_parser import BaseParser, ParseResult


class BBCParser(BaseParser):
    # Non-article URL patterns — return None so trafilatura handles them
    _SKIP_PATTERNS = [
        '/sounds/', '/radio/', '/iplayer/',
        '/sport/live/', '/news/live/', '/news/videos/',
    ]

    def extract(self, soup: BeautifulSoup, article_url: str) -> Optional[ParseResult]:
        # Skip non-article BBC pages
        if any(p in article_url for p in self._SKIP_PATTERNS):
            return None

        container = soup.find("main") or soup.find("article") or soup
        self._remove_unwanted(container)

        # BBC-specific noise removal
        for tag in container.find_all(class_=re.compile(r"Metadata|Share|Related")):
            try:
                tag.decompose()
            except Exception:
                pass

        paragraphs = container.find_all("p")
        article_text = self._clean_paragraphs(paragraphs)  # ← renamed to avoid shadowing
        if not article_text:
            return None

        # ── Title ──────────────────────────────────────────────────────────
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

        # ── Author ─────────────────────────────────────────────────────────
        author = None

        # 1) Meta tags
        for attrs in [
            {"property": "cXenseParse:author"},
            {"name": "author"},
            {"property": "article:author"},
            {"property": "og:author"},
        ]:
            tag = soup.find("meta", attrs)
            if tag and tag.get("content"):
                content = tag["content"].strip()
                if content and not content.startswith("http"):
                    author = content
                    break

        # 2) JSON-LD author
        if not author:
            for script in soup.find_all("script", type="application/ld+json"):
                if not script.string:
                    continue
                try:
                    data = json.loads(script.string)
                    items = data if isinstance(data, list) else [data]
                    for item in items:
                        if not isinstance(item, dict):
                            continue
                        raw_author = item.get("author")
                        if not raw_author:
                            continue
                        if isinstance(raw_author, dict):
                            author = raw_author.get("name", "")
                        elif isinstance(raw_author, list):
                            names = [
                                a.get("name", "") for a in raw_author
                                if isinstance(a, dict) and a.get("name")
                            ]
                            author = "; ".join(names) if names else None
                        elif isinstance(raw_author, str):
                            author = raw_author
                        if author and not author.startswith("http"):
                            break
                        author = None
                    if author:
                        break
                except Exception:
                    continue

        # 3) DOM byline — use a separate variable to avoid shadowing article_text
        if not author:
            byline_candidates = [
                soup.select_one('[data-testid*="byline"]'),
                soup.select_one('[class*="byline"]'),
                soup.select_one('[class*="Contributor"]'),
            ]
            for node in byline_candidates:
                if node:
                    byline_text = node.get_text(" ", strip=True)  # ← separate variable
                    if byline_text and not byline_text.startswith("http"):
                        byline_text = re.sub(r"^By\s+", "", byline_text, flags=re.I).strip()
                        author = byline_text
                        break

        # ── Date ───────────────────────────────────────────────────────────
        published_at = None

        # 1) JSON-LD
        for script in soup.find_all("script", type="application/ld+json"):
            if not script.string:
                continue
            try:
                data = json.loads(script.string)
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    value = item.get("datePublished") or item.get("dateCreated") or item.get("dateModified")
                    if value:
                        published_at = str(value).strip()
                        break
                if published_at:
                    break
            except Exception:
                continue

        # 2) Meta tags — covers news, sport, culture, travel, etc.
        if not published_at:
            for attrs in [
                {"property": "article:published_time"},
                {"property": "article:modified_time"},
                {"property": "og:updated_time"},
                {"name": "pubdate"},
                {"name": "date"},
                {"property": "og:article:published_time"},
                {"itemprop": "datePublished"},
            ]:
                tag = soup.find("meta", attrs)
                if tag:
                    value = tag.get("content") or tag.get("datetime")
                    if value:
                        published_at = value.strip()
                        break

        # 3) <time> tag
        if not published_at:
            time_tag = soup.find("time")
            if time_tag:
                value = time_tag.get("datetime") or time_tag.get_text(" ", strip=True)
                if value:
                    published_at = value.strip()
        
        # 3b) URL slug date — covers /culture/article/YYYYMMDD-slug, /travel/, /future/, etc.
        if not published_at:
            url_date_match = re.search(r'/(\d{8})-', article_url)
            if url_date_match:
                raw = url_date_match.group(1)  # e.g. "20260414"
                published_at = f"{raw[:4]}-{raw[4:6]}-{raw[6:]}T00:00:00"

        # 4) data-testid timestamp (BBC often uses this for culture/travel)
        if not published_at:
            ts_node = soup.select_one('[data-testid*="timestamp"]')
            if ts_node:
                t = ts_node.find("time")
                if t:
                    published_at = t.get("datetime") or t.get_text(" ", strip=True)
                else:
                    published_at = ts_node.get_text(" ", strip=True) or None

        if not title or not author or not published_at:
            print(
                f"[BBCParser WARNING] Partial parse for {article_url} | "
                f"title={bool(title)} author={bool(author)} published={bool(published_at)}"
            )

        return ParseResult(article_text, title, author, published_at)