import datetime
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from logging import Logger, getLogger
from typing import Any, Dict, Optional, List, Tuple
from common.io.json_updater import JsonHandler
from common.models.api.dtos.job import JobStage
from common.models.api.redis_models import StreamMessage
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

class FailedToFetch(Exception):
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)
class FailedToParse(Exception):
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)

class ScraperService(ServiceTemplate):
    """Concurrently scrapes, parses, and publishes messages"""

    def __init__(self, config:ServiceConfig) -> None:
        super().__init__(config)
        self.stats_json_handler = JsonHandler(filename="stats.json")

    def _log_stats(self, fetch_time, parse_time) -> None:
        file_data = self.stats_json_handler.read_json()
        
        total_time = file_data.get("total_time_spent_both", 0)
        
        total_jobs_processed = file_data.get("total_jobs_processed", 0)
        total_jobs_processed += 1
        
        
        if fetch_time:
            number_of_fetch_jobs_processed = file_data.get("number_of_fetch_jobs_processed", 0)
            number_of_fetch_jobs_processed += 1
            
            total_fetch_time = file_data.get("total_time_spent_fetching", 0)

            total_fetch_time += fetch_time

            file_data["number_of_fetch_jobs_processed"] = number_of_fetch_jobs_processed
            file_data["total_time_spent_fetching"] = total_fetch_time
            file_data["avg_fetch_time"] = total_fetch_time / number_of_fetch_jobs_processed

            total_time += fetch_time

        if parse_time:
            number_of_parse_jobs_processed = file_data.get("number_of_parse_jobs_processed", 0)
            number_of_parse_jobs_processed += 1
            
            total_parse_time = file_data.get("total_time_spent_parsing", 0)

            total_parse_time += parse_time
            
            file_data["number_of_parse_jobs_processed"] = number_of_parse_jobs_processed
            file_data["total_time_spent_parsing"] = total_parse_time
            file_data["avg_parse_time"] = total_parse_time / number_of_parse_jobs_processed
            
            total_time += parse_time
        
    
        file_data["total_time_spent_both"] = total_time
        file_data["total_jobs_processed"] = total_jobs_processed 
        file_data["avg_total_time"] = total_time / total_jobs_processed
        
        self.stats_json_handler.write_json(file_data)
        

    def _fetch_article_and_update(self, message: StreamMessage) -> StreamMessage:
        try:
            article_url:Optional[str] = message.link
            if not article_url:
                self.logger.error(f"No link on this message {message}")
                raise FailedToFetch("No link on this message")
                
                
                
            self.logger.debug(f"Attemping to fetch HTML from {article_url}")
            article_html:str = fetch_manager.fetch_article_html(article_url)
            if not article_html:
                raise FailedToFetch("Successful fetch but returned HTML was empty")
            
            
            self.logger.debug(f"Successfully fetched HTML for {article_url}, length: {len(article_html)}")
            message.set_raw_html(article_html)
            return message
        
        except Exception as e:
            self.logger.error(f"\nFinal failure after {MAX_FETCH_RETRIES} attempts... Publishing to failure queue.")
            raise e

    def _parse_article_and_update(self, message: StreamMessage) -> StreamMessage:
        try:
            article_url:Optional[str] = message.link
            article_html:Optional[str] = message.html
            if not article_url:
                self.logger.error(f"No link on this message {message}")
                raise FailedToParse("No link on this message")
            
            if not article_html:
                self.logger.error(f"No html on this message {message}")
                raise FailedToParse("No html on this message")
            
            self.logger.debug(f"Attemping to parse HTML from {article_url}")
            parsed_result:ParseResult= parse_manager.parse_article_raw_html(article_html, article_url, None)
            if not parsed_result:
                raise FailedToFetch("Successful parse but returned text was empty")
            
            self.logger.debug(
                f"Successfully parsed HTML for {article_url}, "
                f"length: {len(parsed_result.text or '')}"
            )
            
            self.logger.debug(parsed_result)
            message.set_parsed_result(parsed_result)
            self.logger.debug("HERE")
            return message
        except Exception as e:
            self.logger.error(f"\nFailed to parse HTML of message. Publishing to failure queue. {e}")
            self.logger.error(f"Stack Trace:\n{traceback.format_exc()}")
            raise e

    def _process_message(self, message: StreamMessage) -> StreamMessage:
        
        try:
            fetch_time, parse_time = None, None
            message.add_timestamp(JobStage.IN)
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
            
            message.add_timestamp(JobStage.OUT)
            self._log_stats(fetch_time, parse_time)
            return message
        
        except FailedToFetch as e:
            raise ProcessingError(f"Failed to fetch {message.link}: {e}")
        
        except FailedToParse as e:
            raise ProcessingError(f"Failed to parse {message.link}: {e}")
    
   