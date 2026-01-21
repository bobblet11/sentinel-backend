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

class MessageSaver():
    def __init__(self,message_store_filename: str = "messages.json", log_directory:Path=Path("/app/logs")):    
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


    def save_new_message(self, message: StreamMessage) -> None:
        new_message_data:Dict[str,Any] = message.data.model_dump()

        try:
            with open(str(self.message_store_filepath), "r") as file:
                file_data = json.load(file)
        except (json.JSONDecodeError, FileNotFoundError):

            file_data = {"messages": []}

        file_data["messages"].append(new_message_data)

        with open(str(self.message_store_filepath), "w") as file:
            json.dump(file_data, file, indent=4)
                