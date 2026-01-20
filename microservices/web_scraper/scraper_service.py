import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from logging import Logger, getLogger
from typing import Any, Dict, Optional, List, Tuple
from common.models.api.dtos.job import JobStage
from common.models.api.redis_models import StreamMessage
from common.redis_client.consumer import RedisConsumer
from common.redis_client.publisher import RedisPublisher
from common.redis_client.publisher_router import RedisPublisherRouter
from common.service.service_template import ProcessingError, ServiceTemplate
from microservices.web_scraper.config import (
    BACKGROUND_OUTPUT_STREAM,
    BATCH_SIZE,
    CONSUMER_NAME,
    FAILURE_OUTPUT_STREAM,
    GROUP_NAME,
    INPUT_STREAM,
    SCRAPER_MAX_WORKERS,
    USER_OUTPUT_STREAM,
    MAX_FETCH_RETRIES
)
from microservices.web_scraper.managers.fetch_manager_selenium import fetch_manager
from microservices.web_scraper.managers.parse_manager import parse_manager, ParseResult


PRIORITY_MAP = {
    "user": 1,
    "admin": 1,  
    "background": 2,
    "logging": 3,
}
LOWEST_PRIORITY: float = float("inf")

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
            message.add_timestamp(JobStage.FETCHED)
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
            parsed_result:Dict[str,str] = parse_manager.parse_article_raw_html(article_html, article_url, None)
            if not parsed_result:
                raise FailedToFetch("Successful parse but returned text was empty")
            
            self.logger.debug(
                f"Successfully parsed HTML for {article_url}, "
                f"length: {len(parsed_result.get('text') or '')}"
            )
            message.set_parsed_text(parsed_result)
            message.add_timestamp(JobStage.PARSED)
            return message
        except Exception as e:
            self.logger.error(f"\nFailed to parse HTML of message. Publishing to failure queue.")
            raise e

    def _process_message(self, message: StreamMessage) -> StreamMessage:
        try:
            fetched_message:StreamMessage = self._fetch_article_and_update(message)
            parsed_message:StreamMessage = self._parse_article_and_update(fetched_message)
            
            return parsed_message
        
        except FailedToFetch as e:
            raise ProcessingError(f"Failed to fetch {message.link}: {e}")
        
        except FailedToParse as e:
            raise ProcessingError(f"Failed to parse {message.link}: {e}")
    
   