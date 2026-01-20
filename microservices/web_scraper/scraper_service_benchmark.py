import json
import os
from pathlib import Path
from typing import Any, Dict, Tuple
from common.models.api.redis_models import StreamMessage
from common.service.service_template import ProcessingError, ServiceConfig
from microservices.web_scraper.scraper_service import ScraperService


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

class ScraperServiceBenchmark(ScraperService):
    """Concurrently scrapes, parses, and publishes messages"""

    def __init__(self,config: ServiceConfig, log_directory:Path=Path("/app/logs")):
        super().__init__(config)  
        message_store_filename:str = f"messages.json"
    
        #create file
        if isinstance(log_directory, str):
            log_directory = Path(log_directory)
        log_directory.mkdir(mode=777,parents=True, exist_ok=True)
        message_store_filepath:Path = log_directory / message_store_filename
        message_store_filepath.touch(mode=777, exist_ok=True)
        os.chmod(str(message_store_filepath), 0o666)
        self.message_store_filepath: Path = message_store_filepath
        
        with open(str(self.message_store_filepath), "r+") as file:
            json.dump({"messages":[]} , file, indent=4)


    def _process_message(self, message: StreamMessage) -> StreamMessage:
        try:
            fetched_message:StreamMessage = self._fetch_article_and_update(message)
            parsed_message:StreamMessage = self._parse_article_and_update(fetched_message)
            new_message:Dict[str,Any] = parsed_message.data.model_dump()

            try:
                with open(str(self.message_store_filepath), "r") as file:
                    file_data = json.load(file)
            except (json.JSONDecodeError, FileNotFoundError):
    
                file_data = {"messages": []}

            file_data["messages"].append(new_message)

            with open(str(self.message_store_filepath), "w") as file:
                json.dump(file_data, file, indent=4)
                
            return parsed_message
        
        except FailedToFetch as e:
            raise ProcessingError(f"Failed to fetch {message.link}: {e}")
        
        except FailedToParse as e:
            raise ProcessingError(f"Failed to parse {message.link}: {e}")
   
    def _process_and_publish_worker(self, message: StreamMessage) -> Tuple[str, str]:
        """Worker for concurrent mode. Processes, then publishes."""
        try:
            self._process_message(message)
            self.message_consumer.acknowledge(message.stream, message.redis_id)
            return "0","0"

        except Exception as e:
            self.logger.error(e)
            raise
