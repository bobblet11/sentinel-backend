from datetime import datetime
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from logging import Logger, getLogger
from typing import Any, Dict, Optional, List, Tuple
from common.io.json_updater import JsonHandler
from common.models.api.dtos.job import JobStage
from common.models.api.redis_models import StreamMessage
from common.models.api.validation_helpers import get_pretty_print_message, get_pretty_print_stream_message, validate_after_webscraper
from common.redis_client.consumer import RedisConsumer
from common.redis_client.publisher import RedisPublisher
from common.redis_client.publisher_router import RedisPublisherRouter
from common.service.service_template import ProcessingError, ServiceConfig, ServiceTemplate
from microservices.web_scraper.config import (
    MAX_FETCH_RETRIES
)
from microservices.web_scraper.managers.fetch_manager_selenium import fetch_manager
from microservices.web_scraper.managers.parse_manager import parse_manager, ParseResult
import traceback
import re
class FailedToFetch(Exception):
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)
class FailedToParse(Exception):
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)



OUTLET_PATTERNS = {
    r"(bbc\.com|bbc\.co\.uk|www\.bbc\.com)": "BBC",
    r"(theguardian\.com|www\.theguardian\.com)": "The Guardian",
    r"(cbc\.ca|www\.cbc\.ca)": "CBC",
    r"(euronews\.com|www\.euronews\.com)": "Euronews",
    r"(abcnews\.go\.com|abcnews\.com)": "ABC",
    r"(cbsnews\.com|www\.cbsnews\.com)": "CBS",
    r"(nbcnews\.com|www\.nbcnews\.com)": "NBC",
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
    """Concurrently scrapes, parses, and publishes messages"""

    def __init__(self, config:ServiceConfig) -> None:
        super().__init__(config)
        self.stats_json_handler = JsonHandler(filename="stats.json")

    def _log_stats(self, fetch_time: Optional[float], parse_time: Optional[float]) -> None:
        data = self.stats_json_handler.read_json()

        # Normalize times
        fetch_time = fetch_time or 0.0
        parse_time = parse_time or 0.0
        total_time = fetch_time + parse_time

        today = datetime.now().date().isoformat()

        # Initialize daily entry if missing
        entry = data.setdefault(today, {
            "total_time_spent_scraping": 0.0,
            "total_time_spent_fetching": 0.0,
            "total_time_spent_parsing": 0.0,

            "number_of_jobs_processed": 0,
            "number_of_articles_fetched": 0,
            "number_of_articles_parsed": 0,

            "jobs_fetch_only": 0,
            "jobs_parse_only": 0,
            "jobs_fetch_and_parse": 0,

            "fetch_errors": 0,
            "parse_errors": 0,

            "min_fetch_time": None,
            "max_fetch_time": None,
            "min_parse_time": None,
            "max_parse_time": None,
        })

        # Update cumulative totals
        entry["total_time_spent_scraping"] += total_time
        entry["total_time_spent_fetching"] += fetch_time
        entry["total_time_spent_parsing"] += parse_time

        # Update job counters
        entry["number_of_jobs_processed"] += 1
        if fetch_time > 0:
            entry["number_of_articles_fetched"] += 1
        if parse_time > 0:
            entry["number_of_articles_parsed"] += 1

        # Classify job type
        if fetch_time > 0 and parse_time > 0:
            entry["jobs_fetch_and_parse"] += 1
        elif fetch_time > 0:
            entry["jobs_fetch_only"] += 1
        elif parse_time > 0:
            entry["jobs_parse_only"] += 1

        # Track min/max fetch time
        if fetch_time > 0:
            entry["min_fetch_time"] = (
                fetch_time if entry["min_fetch_time"] is None
                else min(entry["min_fetch_time"], fetch_time)
            )
            entry["max_fetch_time"] = (
                fetch_time if entry["max_fetch_time"] is None
                else max(entry["max_fetch_time"], fetch_time)
            )

        # Track min/max parse time
        if parse_time > 0:
            entry["min_parse_time"] = (
                parse_time if entry["min_parse_time"] is None
                else min(entry["min_parse_time"], parse_time)
            )
            entry["max_parse_time"] = (
                parse_time if entry["max_parse_time"] is None
                else max(entry["max_parse_time"], parse_time)
            )

        # Prune to last 30 days
        MAX_DAYS = 30
        dates = sorted(data.keys())
        if len(dates) > MAX_DAYS:
            for old_date in dates[:-MAX_DAYS]:
                del data[old_date]

        # Persist
        data[today] = entry
        self.stats_json_handler.write_json(data)


    def _fetch_article_and_update(self, message: StreamMessage) -> StreamMessage:
        try:
            article_url:Optional[str] = message.link
            if not article_url:
                raise FailedToFetch("No link on this message")
        
            self.logger.debug(f"Attempting to fetch HTML for {article_url}")
            article_html:str = fetch_manager.fetch_article_html(article_url)
            if not article_html:
                raise FailedToFetch("Successful fetch but returned HTML was empty")
            
            
            self.logger.debug(f"Successfully fetched HTML for {article_url}, length: {len(article_html)}")
            message.set_raw_html(article_html)
            return message
        
        except Exception as e:
            self.logger.error(f"\nFailed to fetch HTML of message. Publishing to failure queue. {e}")
            raise 

    def _parse_article_and_update(self, message: StreamMessage) -> StreamMessage:
        try:
            article_url:Optional[str] = message.link
            article_html:Optional[str] = message.html
            if not article_url:
                raise FailedToParse("No link on this message")
            if not article_html:
                raise FailedToParse("No html on this message")
            
            self.logger.debug(f"Attempting to parse TEXT for {article_url}")
            parsed_result:ParseResult= parse_manager.parse_article_raw_html(article_html, article_url, None)
            
            if not parsed_result:
                raise FailedToParse("Successful parse but returned text was empty")
            
            self.logger.debug(f"Successfully parsed HTML for {article_url}, length: {len(parsed_result.text or '')}")
            message.set_parsed_result(parsed_result)
            return message
        except Exception as e:
            self.logger.error(f"\nFailed to parse HTML of message. Publishing to failure queue. {e}")
            raise e

    def _process_message(self, message: StreamMessage) -> StreamMessage:
        
        try:
            # maybe this timing needs to be refactored
            fetch_time, parse_time = None, None

            message.add_timestamp(JobStage.WEB_SCRAPE_START)
            
            if not message.html:
                fetch_start = time.perf_counter()
                message.add_timestamp(JobStage.FETCHED_IN)
                message:StreamMessage = self._fetch_article_and_update(message)
                message.add_timestamp(JobStage.FETCHED_OUT)
                fetch_end = time.perf_counter()
                fetch_time = fetch_end - fetch_start
                
            if not message.text:
                parse_start = time.perf_counter()
                message.add_timestamp(JobStage.PARSED_IN)
                message:StreamMessage = self._parse_article_and_update(message)
                message.add_timestamp(JobStage.PARSED_OUT)
                parse_end = time.perf_counter()
                parse_time = parse_end - parse_start

            if message.text:
                text_preview = (message.text[:20] + "...") if len(message.text) > 20 else message.text
                # this might be out of date?
                self.logger.debug(
                    "Scraper has processed one message\n\turl=%s\n\toutlet=%s\n\ttitle=%s\n\tpublish_date=%s\n\ttext_len=%s\n\thtml_len=%s\n\ttext_preview=%s",
                    message.link,
                    message.news_outlet_name,
                    message.title,
                    message.data.payload.publish_date,
                    len(message.text or ""),
                    len(message.html or ""),
                    text_preview,
                )
            
            self._log_stats(fetch_time, parse_time)
            
            matched_outlet = match_outlet_name(message.link or "")
            if matched_outlet:
                message.data.payload.news_outlet = matched_outlet

            self.logger.info(
                "Outlet=%s Author=%s PublishDate=%s",
                message.data.payload.news_outlet,
                message.data.payload.author,
                message.data.payload.publish_date,
            )
            
            message.add_timestamp(JobStage.WEB_SCRAPE_END)
            
            validate_after_webscraper(message)
            self.logger.debug(get_pretty_print_stream_message(message))
            
            return message
        
        except FailedToFetch as e:
            raise ProcessingError(f"Failed to fetch {message.link}: {e}")
        
        except FailedToParse as e:
            raise ProcessingError(f"Failed to parse {message.link}: {e}")
    
   
