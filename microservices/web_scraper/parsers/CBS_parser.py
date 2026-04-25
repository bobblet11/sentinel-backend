# # nyt_scraper.py
# import json
# import re
# from typing import Dict, Optional
# from urllib.parse import urlparse

# from bs4 import BeautifulSoup
# from microservices.web_scraper.parsers.base_parser import BaseParser, ParseResult

# # New York Times


# class CBSParser(BaseParser):
#     def extract(self, soup: BeautifulSoup, article_url: str) -> Optional[ParseResult]:
#         container = (
#             soup.find("article") or
#             soup.find("main") or
#             soup
#         )
#         self._remove_unwanted(container)

#         paragraphs = container.find_all("p")
#         text = self._clean_paragraphs(paragraphs)
#         if not text:
#             return None

#         # title
#         title = None
#         og = soup.find("meta", property="og:title")
#         if og and og.get("content"):
#             title = og["content"].strip()
#         if not title:
#             h1 = soup.find("h1" , {"class" : "content__title"})
#             if h1:
#                 title = h1.get_text(strip=True)

#         if not title and soup.find("title"):
#             title = soup.find("title").string

#         # --- Author & Date (Prioritize Meta, Fallback to DOM) ---
#         author = None
#         published_at = None

#         # 1. Try Meta Tags first (cleanest)
#         time_tag = soup.find("time")
#         if time_tag:
#             published_at = time_tag.get("datetime") or time_tag.get_text(strip=True)

#         meta_author = (
#             soup.find("meta", {"name": "author"}) or
#             soup.find("meta", {"property": "article:author"})
#         )
#         if meta_author and meta_author.get("content"):
#             author = meta_author["content"].strip()

#         # 2. Get from DOM
#         if not author or not published_at:
#             byline_div_author = soup.find("div", class_=re.compile("byline"))
#             byline_div_published = soup.find("div", {"class": "content__meta content__meta--timestamp"})

#             if byline_div_author:
#                 # --- DOM Author Extraction ---
#                 if not author:
#                     # Authors are usually linked in <a> tags within the byline
#                     full_byline_author_text = byline_div_author.get_text(" ", strip=True)

#                     if "By" in full_byline_author_text:
#                         full_byline_author_text = full_byline_author_text.replace("By", "").strip()
#                     author = full_byline_author_text

#             if byline_div_published:
#                 # --- DOM Date Extraction ---
#                 if not published_at:
#                     # The date is just text inside a div, hard to target by class.
#                     # Best approach is Regex on the text content of the whole byline.
#                     full_byline_published_text = byline_div_published.get_text(" ", strip=True)

#                     # Pattern matches: Month DD, YYYY (e.g., December 28, 2025)
#                     # We accept roughly any time format after the year
#                     date_pattern = r"([A-Z][a-z]+ \d{1,2}, \d{4}(?:, \d{1,2}:\d{2} [AP]M)?)"
#                     match = re.search(date_pattern, full_byline_published_text)
#                     if match:
#                         published_at = match.group(1)


#             if not published_at:
#                     meta_pubdate = soup.find("meta", {"name": "pubdate"})
#                     if meta_pubdate and meta_pubdate.get("content"):
#                         published_at = meta_pubdate["content"].strip()
#             if not published_at:
#                 span_date = soup.find("span", {"itemprop": "datePublished"})
#                 if span_date:
#                     published_at = span_date.get("datetime") or span_date.get_text(strip=True)

#             if not published_at:
#                 script_tags = soup.find_all("script", type="application/ld+json")
#                 for script_tag in script_tags:
#                     try:
#                         data = json.loads(script_tag.string)

#                         if isinstance(data, list):
#                             for item in data:
#                                 if isinstance(item, dict) and "datePublished" in item:
#                                     published_at = item["datePublished"]
#                                     break

#                         elif isinstance(data, dict):
#                             published_at = data.get("datePublished")

#                     except Exception:
#                         pass

#         # 3. LAST RESORT (twitter)
#         if not author:
#             meta_author = soup.find("meta", {"name": "twitter:creator"})
#             if meta_author and meta_author.get("content"):
#                 raw = meta_author["content"]
#                 if "x.com" in raw:
#                     author = raw.split("/")[-1]
#                 elif raw.startswith("@"):
#                     author = raw.replace("@", "")
#         if not title or not author or not published_at:
#             print(f"[HARDCODED PARSE ERROR] something is not correct for {article_url}\n\t:text{text}\n\ttitle:{title}\n\tauthor:{author}\n\tpublished:{published_at}")

#         return ParseResult(text, title, author, published_at)
# nyt_scraper.py
import json
import re
from typing import Optional

from bs4 import BeautifulSoup

from microservices.web_scraper.parsers.base_parser import BaseParser, ParseResult


class CBSParser(BaseParser):
    def extract(self, soup: BeautifulSoup, article_url: str) -> Optional[ParseResult]:
        container = soup.find("div", {"class": "container"}) or soup
        self._remove_unwanted(container)

        paragraphs = container.find_all("p")
        text = self._clean_paragraphs(paragraphs)
        if not text:
            return None

        # title
        title = None
        og = soup.find("meta", property="og:title")
        if og and og.get("content"):
            title = og["content"].strip()
        if not title:
            h1 = soup.find("h1", {"class": "content__title"})
            if h1:
                title = h1.get_text(strip=True)

        if not title and soup.find("title"):
            title = soup.find("title").string

        # --- Author & Date (Prioritize JSON-LD FIRST, then fallback) ---
        author = None
        published_at = None

        # =========================
        # 1. JSON-LD PRIMARY SOURCE
        # =========================
        script_tags = soup.find_all("script", type="application/ld+json")

        def extract_date(obj):
            if isinstance(obj, dict):
                if obj.get("datePublished"):
                    return obj["datePublished"]
                if "@graph" in obj:
                    for item in obj["@graph"]:
                        result = extract_date(item)
                        if result:
                            return result
            elif isinstance(obj, list):
                for item in obj:
                    result = extract_date(item)
                    if result:
                        return result
            return None

        def extract_author(obj):
            if isinstance(obj, dict):
                if obj.get("author"):
                    author = obj["author"]
                    if isinstance(author, dict):
                        return author.get("name")
                    elif isinstance(author, list):
                        return ", ".join(
                            [a.get("name") for a in author if isinstance(a, dict)]
                        )
                    return author
                if "@graph" in obj:
                    for item in obj["@graph"]:
                        result = extract_author(item)
                        if result:
                            return result
            elif isinstance(obj, list):
                for item in obj:
                    result = extract_author(item)
                    if result:
                        return result
            return None

        for script_tag in script_tags:
            if not script_tag.string:
                continue
            try:
                data = json.loads(script_tag.string)

                if not published_at:
                    published_at = extract_date(data)

                if not author:
                    author = extract_author(data)

                if published_at and author:
                    break

            except Exception:
                continue

        # =========================
        # 2. META / TIME FALLBACK
        # =========================
        if not published_at:
            time_tag = soup.find("time")
            if time_tag:
                published_at = time_tag.get("datetime") or time_tag.get_text(strip=True)

        meta_author = soup.find("meta", {"name": "author"}) or soup.find(
            "meta", {"property": "article:author"}
        )
        if meta_author and meta_author.get("content"):
            if not author:
                author = meta_author["content"].strip()

        # =========================
        # 3. DOM FALLBACK
        # =========================
        if not author or not published_at:
            byline_div_author = soup.find("div", class_=re.compile("byline"))
            byline_div_published = soup.find("div", class_=re.compile("timestamp"))

            if byline_div_author and not author:
                full_byline_author_text = byline_div_author.get_text(" ", strip=True)
                if "By" in full_byline_author_text:
                    full_byline_author_text = full_byline_author_text.replace(
                        "By", ""
                    ).strip()
                author = full_byline_author_text

            if byline_div_published and not published_at:
                full_byline_published_text = byline_div_published.get_text(
                    " ", strip=True
                )
                date_pattern = r"([A-Z][a-z]+ \d{1,2}, \d{4}(?:, \d{1,2}:\d{2} [AP]M)?)"
                match = re.search(date_pattern, full_byline_published_text)
                if match:
                    published_at = match.group(1)

        # =========================
        # 4. EXTRA FALLBACKS
        # =========================
        if not published_at:
            meta_pubdate = soup.find("meta", {"name": "pubdate"})
            if meta_pubdate and meta_pubdate.get("content"):
                published_at = meta_pubdate["content"].strip()

        if not published_at:
            span_date = soup.find("span", {"itemprop": "datePublished"})
            if span_date:
                published_at = span_date.get("datetime") or span_date.get_text(
                    strip=True
                )

        # =========================
        # 5. LAST RESORT (twitter)
        # =========================
        if not author:
            meta_author = soup.find("meta", {"name": "twitter:creator"})
            if meta_author and meta_author.get("content"):
                raw = meta_author["content"]
                if "x.com" in raw:
                    author = raw.split("/")[-1]
                elif raw.startswith("@"):
                    author = raw.replace("@", "")

        if author:
            author = re.sub(r"\s+", " ", author).strip()

        if not title or not author or not published_at:
            print(
                f"[HARDCODED PARSE ERROR] something is not correct for {article_url}\n\t:text{text}\n\ttitle:{title}\n\tauthor:{author}\n\tpublished:{published_at}"
            )

        return ParseResult(text, title, author, published_at)
