import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from logging import Logger, getLogger
from typing import Any, Dict, Optional, List

from common.models.api.redis_models import StreamMessage
from common.redis_client.consumer import RedisConsumer
from common.redis_client.publisher import RedisPublisher
from common.redis_client.publisher_router import RedisPublisherRouter
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
from microservices.web_scraper.managers.parse_manager import parse_manager

SERVICE_NAME="scraper"
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

class ScraperService:
    """Concurrently scrapes, parses, and publishes messages"""
    
    routing_map = {"user": USER_OUTPUT_STREAM, "background": BACKGROUND_OUTPUT_STREAM}

    def __init__(self) -> None:
        self.logger: Logger = getLogger(SERVICE_NAME)
        self.keep_running: bool = True
        self.message_consumer = RedisConsumer(INPUT_STREAM, GROUP_NAME, CONSUMER_NAME)
        self.sucess_publisher = RedisPublisherRouter(
            routing_key="type", routing_map=self.routing_map
        )
        self.fail_publisher = RedisPublisher(FAILURE_OUTPUT_STREAM)

    def shutdown(self, *args) -> None:
        """Signal handler to initiate a graceful shutdown."""
        self.logger.info("\nShutdown signal received. Finishing current batch...")
        self.keep_running = False

    def _parse_message(self, raw_msg: Dict[str, Any]) -> StreamMessage:
        """Converts raw Redis dict to a typed Dataclass and calculates priority."""
        msg_data:Dict[str, Any] = raw_msg.get("data", {})
        msg_type:str = msg_data.get("header", {}).get("type")
        
        # Calculate priority once during parsing
        priority: int | float = PRIORITY_MAP.get(msg_type, LOWEST_PRIORITY)
        
        return StreamMessage(
            stream=raw_msg["stream"],
            redis_id=raw_msg["redis_message_id"],
            data=msg_data,
            priority=priority
        )
    
    def _publish_and_ack_worker(
        self, message: StreamMessage, publisher: RedisPublisherRouter | RedisPublisher
    ) -> int:
        """
        The "worker" function for a single thread.
        It publishes one message and, if successful, acknowledges it.
        """
        return message
        stream = message["stream"]
        redis_msg_id = message["redis_message_id"]
        message_data = message["data"]

        try:
            if not publisher.publish_one(message_data):
                raise RuntimeError(
                    f"Failed to publish message {redis_msg_id} to stream"
                )

            self.message_consumer.acknowledge(stream, redis_msg_id)

            return message
        except Exception as e:
            self.logger.error(f"  [ERROR] Worker failed for message {redis_msg_id}: {e}")
            raise e

    def _fetch_article_and_update(self, message: StreamMessage) -> StreamMessage:
        try:
            article_url:Optional[str] = message.link
            if not article_url:
                self.logger.error(f"No link on this message {message}")
                raise FailedToFetch("No link on this message")
                
            self.logger.debug(f"Attemping to fetch HTML from {article_url}")
            article_html:str = fetch_manager.fetch_article_html(article_url)
            
            if not article_html:
                raise FailedToFetch("Fetched HTML was empty")
            
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

            parsed_text:str = parse_manager.parse_article_html(article_html, article_url)
            self.logger.debug(f"Successfully parsed HTML for {article_url}, length: {len(parsed_text)}")
            message.set_parsed_text(parsed_text)
            return message
        except Exception as e:
            self.logger.error(f"\nFailed to parse HTML of message. Publishing to failure queue.")
            raise e

    def _fetch_and_parse_message(self, message: StreamMessage):
        try:
            fetched_message:StreamMessage = self._fetch_article_and_update(message)
            parsed_message:StreamMessage = self._parse_article_and_update(fetched_message)
            return self._publish_and_ack_worker(parsed_message, self.sucess_publisher)
        
        except FailedToFetch as e:
            return self._publish_and_ack_worker(message, self.fail_publisher)
        
        except FailedToParse as e:
            return self._publish_and_ack_worker(message, self.fail_publisher)
    
    def _process_batch(self, executor: ThreadPoolExecutor, raw_messages: List[Dict[str,Any]]):
        
        stream_messages: List[StreamMessage] = [self._parse_message(m) for m in raw_messages]
        
        parsed_message_futures = {
            executor.submit(self._fetch_and_parse_message, msg): msg for msg in stream_messages
        }

        for future in as_completed(parsed_message_futures):
            original_message:StreamMessage = parsed_message_futures[future]
            redis_id = original_message.redis_id
            try:
                future.result()
                self.logger.debug(f"Successfully published and acknowledged Msg ID {redis_id}")
            except Exception:
                self.logger.error(f"Could not process message {redis_id}. Message was acknowledged and placed in the failure queue")
    
    def run(self):
        """
        Main execution loop. Fetches and processes messages concurrently.
        """
        self.logger.info(f"Service started. Listening on {INPUT_STREAM}")
        
        with ThreadPoolExecutor(max_workers=SCRAPER_MAX_WORKERS) as executor:
            while self.keep_running:
                try:
                    # 0. Check & deal with pending messagess
                    self.logger.info(f"Checking for pending messages...")
                    pending_messages:List[Dict[str, Any]] = self.message_consumer.consume_pending()
                    if pending_messages:
                        self.logger.info(f"Found {len(pending_messages)} pending messages. Processing them...")
                        self._process_batch(executor, pending_messages)

                    
                    # 1. Fetch
                    self.logger.info(f"Waiting for up to {BATCH_SIZE} messages...")
                    raw_messages:List[Dict[str, Any]] = []
                    while True:
                        raw_messages = self.message_consumer.consume_many(
                            num_to_consume=BATCH_SIZE, block=2000
                        )   
                        if not raw_messages:
                            time.sleep(2)
                            continue
                        break
                    
                    self.logger.info(f"Found {len(raw_messages)} messages. Processing them...")
                    self._process_batch(executor, raw_messages)
                    
                except Exception as e:
                    self.logger.error(f"Unexpected error in main loop {e}")
                    self.shutdown()
                
        self.logger.info("SHUTTING DOWN")
        

