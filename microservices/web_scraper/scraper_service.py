"""Web content extraction service for news articles.

This module implements the web scraper microservice, which fetches and parses
article HTML from URLs using browser automation (Selenium) and multiple parsing
strategies (hardcoded parsers, trafilatura, fallback DOM extraction).

The ScraperService processes Redis stream messages containing article URLs,
extracts the full HTML, parses content (title, body text, author, publish date),
and routes enriched messages to the next pipeline stage (NLP processing).

Key Features:
    - Browser automation with proxy rotation and anti-bot evasion
    - Multi-strategy parsing with fallback handling
    - Automatic outlet/news-source detection
    - Performance metrics collection (fetch time, parse time, HTML/text sizes)
    - Error handling with detailed failure stream routing
"""
import re
import time
from datetime import datetime
from typing import Optional

from common.io.json_updater import JsonHandler
from common.models.api.dtos.job import JobStage
from common.models.api.redis_models import StreamMessage
from common.models.api.validation_helpers import (
    get_pretty_print_stream_message,
    validate_after_webscraper,
)
from common.service.service_template import ServiceConfig, ServiceTemplate
from microservices.web_scraper.managers.fetch_manager_selenium import fetch_manager
from microservices.web_scraper.managers.parse_manager import ParseResult, parse_manager


class ScraperError(Exception):
    def __init__(self, message, url=None, stage=None, details=None):
        super().__init__(message)
        self.url = url
        self.stage = stage
        self.details = details

    def __str__(self):
        base = super().__str__()
        extras = []
        if self.url:
            extras.append(f"url={self.url}")
        if self.stage:
            extras.append(f"stage={self.stage}")
        if self.details:
            extras.append(f"details={self.details}")
        return f"{base} ({', '.join(extras)})"


class FailedToFetch(ScraperError):
    def __init__(self, message, url=None, stage=None, details=None):
        new_message = message + "(Failed to fetch)"
        super().__init__(new_message, url, stage, details)


class FailedToParse(ScraperError):
    def __init__(self, message, url=None, stage=None, details=None):
        new_message = message + "(Failed to parse)"
        super().__init__(new_message, url, stage, details)


OUTLET_PATTERNS = {
    r"(bbc\.com|bbc\.co\.uk|www\.bbc\.com)": "BBC",
    r"(theguardian\.com|www\.theguardian\.com)": "The Guardian",
    r"(cbc\.ca|www\.cbc\.ca)": "CBC",
    r"(euronews\.com|www\.euronews\.com)": "Euronews",
    r"(abcnews\.go\.com|abcnews\.com)": "ABC",
    r"(cbsnews\.com|www\.cbsnews\.com)": "CBS",
    r"(nbcnews\.com|www\.nbcnews\.com|feeds\.nbcnews\.com)": "NBC",
    r"(npr\.org|www\.npr\.org)": "NPR",
    r"(foxnews\.com|www\.foxnews\.com)": "Fox News",
    r"(reuters\.com|www\.reuters\.com)": "Reuters",
    r"(apnews\.com|www\.apnews\.com)": "AP News",
    r"(aljazeera\.com|www\.aljazeera\.com)": "Al Jazeera",
}


def match_outlet_name(article_url: str) -> Optional[str]:
    for pattern, outlet in OUTLET_PATTERNS.items():
        if re.search(pattern, article_url):
            return outlet
    return None


class ScraperService(ServiceTemplate):
    """Main web scraping service for article content extraction.

    Inherits from ServiceTemplate to handle Redis stream consumption. Orchestrates
    HTML fetching and parsing for news articles, collecting performance metrics and
    routing failures appropriately.

    Attributes:
        stats_json_handler: JSON file handler for persisting daily performance stats.
    """

    def __init__(self, config: ServiceConfig) -> None:
        """Initialize the scraper service with config and stats handler.

        Args:
            config: ServiceConfig with service name, stream names, and worker pool size.
        """
        super().__init__(config)
        self.stats_json_handler = JsonHandler(filename="stats.json")

    def _log_stats(
        self,
        outlet: str,
        html_len: int,
        text_len: int,
        fetch_time: Optional[float],
        parse_time: Optional[float],
        error_type: Optional[str] = None,
    ) -> None:
        """Record performance metrics for daily statistics tracking.

        Updates rolling 30-day JSON statistics with fetch times, parse times, HTML
        and text sizes, errors per outlet. Maintains min/max timings and error counts.

        Args:
            outlet: News outlet name (e.g., "BBC", "Reuters", "Unknown").
            html_len: Size in bytes of fetched HTML.
            text_len: Size in bytes of extracted article text.
            fetch_time: Seconds elapsed for HTTP fetch (None if skipped).
            parse_time: Seconds elapsed for HTML parsing (None if skipped).
            error_type: Exception class name if processing failed (None on success).
        """
        data = self.stats_json_handler.read_json()

        # Normalize times
        fetch_time = fetch_time or 0.0
        parse_time = parse_time or 0.0
        fetch_time + parse_time

        html_len = html_len or 0
        text_len = text_len or 0

        day_key = datetime.now().date().isoformat()

        # Initialize daily entry if missing
        entry = data.setdefault(
            day_key,
            {
                # total counts
                "jobs_processed": 0,
                "total_time_s": 0.0,
                "total_fetch_time_s": 0.0,
                "total_parse_time_s": 0.0,
                "total_html_size": 0,
                "total_text_size": 0,
                "errors": {},
                "outlet_stats": {},
                "min_fetch_time_s": None,
                "max_fetch_time_s": None,
                "min_parse_time_s": None,
                "max_parse_time_s": None,
            },
        )

        # Update global totals
        entry["jobs_processed"] += 1
        entry["total_time_s"] += fetch_time + parse_time
        entry["total_fetch_time_s"] += fetch_time
        entry["total_parse_time_s"] += parse_time
        entry["total_html_size"] += html_len
        entry["total_text_size"] += text_len

        # Update min max
        if fetch_time > 0:
            entry["min_fetch_time_s"] = (
                fetch_time
                if entry["min_fetch_time_s"] is None
                else min(entry["min_fetch_time_s"], fetch_time)
            )
            entry["max_fetch_time_s"] = (
                fetch_time
                if entry["max_fetch_time_s"] is None
                else max(entry["max_fetch_time_s"], fetch_time)
            )
        if parse_time > 0:
            entry["min_parse_time_s"] = (
                parse_time
                if entry["min_parse_time_s"] is None
                else min(entry["min_parse_time_s"], parse_time)
            )
            entry["max_parse_time_s"] = (
                parse_time
                if entry["max_parse_time_s"] is None
                else max(entry["max_parse_time_s"], parse_time)
            )

        # Update outlet
        outlet_entry = entry["outlet_stats"].setdefault(
            outlet,
            {
                "jobs": 0,
                "total_time_s": 0.0,
                "total_fetch_time_s": 0.0,
                "total_parse_time_s": 0.0,
                "total_html_size": 0,
                "total_text_size": 0,
                "errors": {},
                "min_fetch_time_s": None,
                "max_fetch_time_s": None,
                "min_parse_time_s": None,
                "max_parse_time_s": None,
            },
        )

        outlet_entry["jobs"] += 1
        outlet_entry["total_time_s"] += fetch_time + parse_time
        outlet_entry["total_fetch_time_s"] += fetch_time
        outlet_entry["total_parse_time_s"] += parse_time
        outlet_entry["total_html_size"] += html_len
        outlet_entry["total_text_size"] += text_len

        if error_type:
            outlet_entry["errors"][error_type] = (
                outlet_entry["errors"].get(error_type, 0) + 1
            )
            entry["errors"][error_type] = entry["errors"].get(error_type, 0) + 1

        # Update min max
        if fetch_time > 0:
            outlet_entry["min_fetch_time_s"] = (
                fetch_time
                if outlet_entry["min_fetch_time_s"] is None
                else min(outlet_entry["min_fetch_time_s"], fetch_time)
            )
            outlet_entry["max_fetch_time_s"] = (
                fetch_time
                if outlet_entry["max_fetch_time_s"] is None
                else max(outlet_entry["max_fetch_time_s"], fetch_time)
            )
        if parse_time > 0:
            outlet_entry["min_parse_time_s"] = (
                parse_time
                if outlet_entry["min_parse_time_s"] is None
                else min(outlet_entry["min_parse_time_s"], parse_time)
            )
            outlet_entry["max_parse_time_s"] = (
                parse_time
                if outlet_entry["max_parse_time_s"] is None
                else max(outlet_entry["max_parse_time_s"], parse_time)
            )

        # Prune to last 30 days
        MAX_DAYS = 30
        dates = sorted(data.keys())
        if len(dates) > MAX_DAYS:
            for old_date in dates[:-MAX_DAYS]:
                del data[old_date]

        # Persist
        data[day_key] = entry
        self.stats_json_handler.write_json(data)

    def _fetch_article_and_update(self, message: StreamMessage) -> StreamMessage:
        """Fetch article HTML from URL using Selenium with proxy rotation.

        Calls FetchManager to retrieve full HTML, validates non-empty result, and
        stores in message. Raises FailedToFetch on empty HTML or missing URL.

        Args:
            message: Stream message containing article URL (message.link).

        Returns:
            Updated message with raw_html populated.

        Raises:
            FailedToFetch: If URL missing, fetch fails, or HTML is empty.
        """
        try:
            article_url: Optional[str] = message.link
            if not article_url:
                raise FailedToFetch(
                    "No link on this message",
                    message.link,
                    "fetching",
                    f"message url is {article_url}",
                )

            self.logger.debug(f"Attempting to fetch HTML for {article_url}")
            article_html: str = fetch_manager.fetch_article_html(article_url)
            if not article_html.strip():
                raise FailedToFetch(
                    "Fetch returned empty HTML (likely anti-bot or timing issue)",
                    message.link,
                    "fetching",
                    f"extracted html is {article_html}",
                )

            self.logger.debug(
                f"Successfully fetched HTML for {article_url}, length: {len(article_html)}"
            )
            message.set_raw_html(article_html)
            return message

        except Exception as e:
            self.logger.error(f"Failed to fetch HTML: {e}")
            raise

    def _parse_article_and_update(self, message: StreamMessage) -> StreamMessage:
        """Parse HTML into structured article fields (text, title, author, date).

        Calls ParseManager which tries hardcoded parsers, trafilatura, and fallback
        DOM extraction. Validates text length > 0 and stores result in message.

        Args:
            message: Stream message with html populated and article URL.

        Returns:
            Updated message with parsed_result (ParseResult) stored.

        Raises:
            FailedToParse: If URL/HTML missing, parse fails, or resulting text is empty.
        """
        try:
            article_url: Optional[str] = message.link
            article_html: Optional[str] = message.html
            if not article_url:
                raise FailedToParse(
                    "No link on this message",
                    message.link,
                    "parsing",
                    f"message url is {article_url}",
                )
            if not article_html:
                raise FailedToParse(
                    "No html on this message",
                    message.link,
                    "parsing",
                    f"message html is {article_html}",
                )

            self.logger.debug(f"Attempting to parse TEXT for {article_url}")
            parsed_result: ParseResult = parse_manager.parse_article_raw_html(
                article_html, article_url, None
            )

            if not parsed_result:
                raise FailedToParse(
                    "Successful parse but returned text was empty",
                    message.link,
                    "parsing",
                    f"article text is {parsed_result}",
                )

            self.logger.debug(
                f"Successfully parsed HTML for {article_url}, length: {len(parsed_result.text or '')}"
            )
            message.set_parsed_result(parsed_result)
            return message
        except Exception as e:
            self.logger.error(f"Failed to parse HTML: {e}")
            raise e

    def _process_message(self, message: StreamMessage) -> StreamMessage:
        """Process a single article through fetch and parse stages.

        Main orchestration method. Detects outlet name, fetches HTML (if needed),
        parses to text/metadata (if needed), adds timestamps, validates output,
        logs statistics, and raises exceptions on failure for failure stream routing.

        Args:
            message: Redis stream message with article URL (message.link).

        Returns:
            Enriched message with html and parsed_result populated.

        Raises:
            FailedToFetch: If URL fetch fails after retries.
            FailedToParse: If HTML parsing fails.
        """

        fetch_time, parse_time, html_len, text_len, error_type = (
            None,
            None,
            None,
            None,
            None,
        )
        matched_outlet = message.data.payload.news_outlet
        if not matched_outlet:
            matched_outlet = match_outlet_name(message.link or "") or "Unknown"
            message.data.payload.news_outlet = matched_outlet

        try:
            message.add_timestamp(JobStage.WEB_SCRAPE_START)

            # may raise
            if not message.html:
                fetch_start = time.perf_counter()
                message.add_timestamp(JobStage.FETCHED_IN)
                message: StreamMessage = self._fetch_article_and_update(message)
                message.add_timestamp(JobStage.FETCHED_OUT)
                fetch_end = time.perf_counter()
                fetch_time = fetch_end - fetch_start
                html_len = len(message.html or "")

            # may raise
            if not message.text:
                parse_start = time.perf_counter()
                message.add_timestamp(JobStage.PARSED_IN)
                message: StreamMessage = self._parse_article_and_update(message)
                message.add_timestamp(JobStage.PARSED_OUT)
                parse_end = time.perf_counter()
                parse_time = parse_end - parse_start

                text_len = len(message.text or "")

            text_preview = (
                (message.text[:20] + "...") if len(message.text) > 20 else message.text
            )
            # this might be out of date?
            self.logger.debug(
                "Scraper has processed one message\n\turl=%s\n\toutlet=%s\n\tauthor=%s\n\ttitle=%s\n\tpublish_date=%s\n\ttext_len=%s\n\thtml_len=%s\n\ttext_preview=%s",
                message.link,
                message.news_outlet_name,
                message.data.payload.author,
                message.title,
                message.data.payload.publish_date,
                len(message.text or ""),
                len(message.html or ""),
                text_preview,
            )

            message.add_timestamp(JobStage.WEB_SCRAPE_END)
            validate_after_webscraper(stream_message=message, message=None)

            self.logger.debug(get_pretty_print_stream_message(message))
            self._log_stats(matched_outlet, html_len, text_len, fetch_time, parse_time)
            return message

        except Exception as e:
            error_type = type(e).__name__
            self._log_stats(
                matched_outlet, html_len, text_len, fetch_time, parse_time, error_type
            )
            raise
