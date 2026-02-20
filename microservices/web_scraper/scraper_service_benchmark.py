import json
import os
from pathlib import Path
from typing import Any, Dict, Tuple
from common.io.save_message import MessageSaver
from common.models.api.dtos.job import JobStage
from common.models.api.redis_models import StreamMessage
from common.service.service_template import ProcessingError, ServiceConfig
from microservices.web_scraper.scraper_service import ScraperService


class FailedToFetch(Exception):
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)
class FailedToParse(Exception):
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)

class ScraperServiceBenchmark(ScraperService):
    """Concurrently scrapes, parses, and publishes messages"""

    def __init__(self,config: ServiceConfig, message_store_filename: str = "messages.json", log_directory:Path=Path("/app/logs")):
        super().__init__(config)  
        self.message_saver = MessageSaver(group_name="scrape_group", message_store_filename=message_store_filename, log_directory=log_directory)


    def _process_message(self, message: StreamMessage) -> StreamMessage:
        try:
            message.add_timestamp(JobStage.IN)
            
            message.add_timestamp(JobStage.FETCHED_IN)
            fetched_message:StreamMessage = self._fetch_article_and_update(message)
            message.add_timestamp(JobStage.FETCHED_OUT)
            message.add_timestamp(JobStage.PARSED_IN)
            parsed_message:StreamMessage = self._parse_article_and_update(fetched_message)
            message.add_timestamp(JobStage.PARSED_OUT)
            
            message.add_timestamp(JobStage.OUT)
            self.message_saver.save_new_message(parsed_message)
            return parsed_message
        
        except FailedToFetch as e:
            raise ProcessingError(f"Failed to fetch {message.link}: {e}")
        
        except FailedToParse as e:
            raise ProcessingError(f"Failed to parse {message.link}: {e}")
   
    def _process_and_publish_worker(self, message: StreamMessage) -> Tuple[str, str]:
        #Ack but dont publish
        try:
            self._process_message(message)
            self.message_consumer.acknowledge_and_delete(message.stream, message.redis_id)
            return "0","0"

        except Exception as e:
            # Catch any exception, including ProcessingError, and route to failure.
            self._handle_failure(message, e)
            # Raise it again so as_completed knows the future failed
            raise
	