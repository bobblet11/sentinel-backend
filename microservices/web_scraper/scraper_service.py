import re
import time
from datetime import datetime
from typing import Optional

from common.io.json_updater import JsonHandler
from common.models.api.dtos.job import JobStage
from common.models.api.redis_models import StreamMessage
from common.models.api.validation_helpers import (
    get_pretty_print_stream_message, validate_after_webscraper)
from common.service.service_template import ServiceConfig, ServiceTemplate
from microservices.web_scraper.managers.fetch_manager_selenium import \
    fetch_manager
from microservices.web_scraper.managers.parse_manager import (ParseResult,
                                                              parse_manager)


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
    """Concurrently scrapes, parses, and publishes messages"""

    def __init__(self, config:ServiceConfig) -> None:
        super().__init__(config)
        self.stats_json_handler = JsonHandler(filename="stats.json")

    def _log_stats(self, outlet:str, html_len:int, text_len:int, fetch_time: Optional[float], parse_time: Optional[float], error_type: Optional[str] = None) -> None:
        data = self.stats_json_handler.read_json()

        # Normalize times
        fetch_time = fetch_time or 0.0
        parse_time = parse_time or 0.0
        fetch_time + parse_time
        
        html_len = html_len or 0
        text_len = text_len or 0
        
        day_key = datetime.now().date().isoformat()

        # Initialize daily entry if missing
        entry = data.setdefault(day_key, {
            # total counts
            "jobs_processed" : 0,
            
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
            "max_parse_time_s": None
        })

        
        # Update global totals
        entry["jobs_processed"] += 1
        entry["total_time_s"] += fetch_time + parse_time
        entry["total_fetch_time_s"] += fetch_time
        entry["total_parse_time_s"] += parse_time
        entry["total_html_size"] += html_len
        entry["total_text_size"] += text_len
        
        # Update min max
        if fetch_time > 0:
            entry["min_fetch_time_s"] = fetch_time if entry["min_fetch_time_s"] is None else min(entry["min_fetch_time_s"], fetch_time)
            entry["max_fetch_time_s"] = fetch_time if entry["max_fetch_time_s"] is None else max(entry["max_fetch_time_s"], fetch_time)
        if parse_time > 0:
            entry["min_parse_time_s"] = parse_time if entry["min_parse_time_s"] is None else min(entry["min_parse_time_s"], parse_time)
            entry["max_parse_time_s"] = parse_time if entry["max_parse_time_s"] is None else max(entry["max_parse_time_s"], parse_time)


        # Update outlet
        outlet_entry = entry["outlet_stats"].setdefault(outlet, {
            "jobs": 0,
            "total_time_s" : 0.0,
            "total_fetch_time_s": 0.0,
            "total_parse_time_s": 0.0,
            "total_html_size": 0,
            "total_text_size": 0,
            "errors": {},
            
            "min_fetch_time_s": None,
            "max_fetch_time_s": None,
            "min_parse_time_s": None,
            "max_parse_time_s": None
        })
        
        outlet_entry["jobs"] += 1
        outlet_entry["total_time_s"] += fetch_time + parse_time
        outlet_entry["total_fetch_time_s"] += fetch_time
        outlet_entry["total_parse_time_s"] += parse_time
        outlet_entry["total_html_size"] += html_len
        outlet_entry["total_text_size"] += text_len

        if error_type:
            outlet_entry["errors"][error_type] = outlet_entry["errors"].get(error_type, 0) + 1
            entry["errors"][error_type] = entry["errors"].get(error_type, 0) + 1
            
        # Update min max
        if fetch_time > 0:
            outlet_entry["min_fetch_time_s"] = fetch_time if outlet_entry["min_fetch_time_s"] is None else min(outlet_entry["min_fetch_time_s"], fetch_time)
            outlet_entry["max_fetch_time_s"] = fetch_time if outlet_entry["max_fetch_time_s"] is None else max(outlet_entry["max_fetch_time_s"], fetch_time)
        if parse_time > 0:
            outlet_entry["min_parse_time_s"] = parse_time if outlet_entry["min_parse_time_s"] is None else min(outlet_entry["min_parse_time_s"], parse_time)
            outlet_entry["max_parse_time_s"] = parse_time if outlet_entry["max_parse_time_s"] is None else max(outlet_entry["max_parse_time_s"], parse_time)

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
        try:
            article_url:Optional[str] = message.link
            if not article_url:
                raise FailedToFetch("No link on this message", message.link, "fetching", f"message url is {article_url}")
        
            self.logger.debug(f"Attempting to fetch HTML for {article_url}")
            article_html:str = fetch_manager.fetch_article_html(article_url)
            if not article_html.strip():
                raise FailedToFetch("Fetch returned empty HTML (likely anti-bot or timing issue)", message.link, "fetching", f"extracted html is {article_html}")

            self.logger.debug(f"Successfully fetched HTML for {article_url}, length: {len(article_html)}")
            message.set_raw_html(article_html)
            return message
        
        except Exception as e:
            self.logger.error(f"Failed to fetch HTML: {e}")
            raise 

    def _parse_article_and_update(self, message: StreamMessage) -> StreamMessage:
        try:
            article_url:Optional[str] = message.link
            article_html:Optional[str] = message.html
            if not article_url:
                raise FailedToParse("No link on this message", message.link, "parsing", f"message url is {article_url}")
            if not article_html:
                raise FailedToParse("No html on this message", message.link, "parsing", f"message html is {article_html}")
            
            self.logger.debug(f"Attempting to parse TEXT for {article_url}")
            parsed_result:ParseResult= parse_manager.parse_article_raw_html(article_html, article_url, None)
            
            if not parsed_result:
                raise FailedToParse("Successful parse but returned text was empty", message.link, "parsing", f"article text is {parsed_result}")
            
            self.logger.debug(f"Successfully parsed HTML for {article_url}, length: {len(parsed_result.text or '')}")
            message.set_parsed_result(parsed_result)
            return message
        except Exception as e:
            self.logger.error(f"Failed to parse HTML: {e}")
            raise e

    def _process_message(self, message: StreamMessage) -> StreamMessage:
        
        fetch_time, parse_time, html_len, text_len, error_type = None, None, None, None, None
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
                message:StreamMessage = self._fetch_article_and_update(message)
                message.add_timestamp(JobStage.FETCHED_OUT)
                fetch_end = time.perf_counter()
                fetch_time = fetch_end - fetch_start
                html_len = len(message.html or "")
                
            # may raise    
            if not message.text:
                parse_start = time.perf_counter()
                message.add_timestamp(JobStage.PARSED_IN)
                message:StreamMessage = self._parse_article_and_update(message)
                message.add_timestamp(JobStage.PARSED_OUT)
                parse_end = time.perf_counter()
                parse_time = parse_end - parse_start
                
                text_len = len(message.text or "")
                
            text_preview = (message.text[:20] + "...") if len(message.text) > 20 else message.text
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
            self._log_stats(matched_outlet, html_len, text_len, fetch_time, parse_time, error_type)    
            raise 

   
