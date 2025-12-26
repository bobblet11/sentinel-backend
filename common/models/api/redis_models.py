from typing import Any, Union, Dict, Optional
from dataclasses import dataclass
from pydantic import BaseModel

"""
In redis, each message looks like this
            some redis_ID
                |
                V
        1730908200123-0 : {
            "payload": {
                "header": {
                    "message_id": "ab12...cd34",
                    "timestamp": "2025-11-06T22:30:00.123456",
                    "type": "background"
                },
                "data": {
                    "url": "http://example.com/article1",
                    "source_rss": "Example News Feed"
                }
            }
        }

"""


class MessageHeader(BaseModel):
    """
    Represents the basic information used to identify and get stats on Messages
    """

    message_id: str
    timestamp: str
    type: str


class MessageURLPayload(BaseModel):
    """
    Represents the payload between ingestor and web scraper service
    """

    url: str
    source_rss: str


class Message(BaseModel):
    """
    Represents the actual message data type passed through a message queue
    """

    header: MessageHeader
    data: Union[MessageURLPayload, Any]  # Fixed for Python 3.9

@dataclass
class StreamMessage:
    stream: str
    redis_id: str
    data: Dict[str, Any]
    priority: Union[int, float]

    @property
    def type(self) -> Optional[str]:
        return self.data.get("header", {}).get("type", None)
    
    @property
    def link(self) -> Optional[str]:
        return self.data.get("data", {}).get("url", None)

    @property
    def html(self) -> Optional[str]:
        return self.data.get("data", {}).get("html", None)

    
    def set_raw_html(self, page_html: str) -> None:
        """
        sets the raw_html
        """
        self.data.setdefault("data", {})["html"] = page_html
    
    def set_parsed_text(self, parsed_text: str) -> None:
        """
        sets the raw_html
        """
        self.data.setdefault("data", {})["text"] = parsed_text
    
    def set_nested(self, value: Any, *keys: str) -> None:
        """
        Sets a value deep inside the data dictionary.
        Creates intermediate dictionaries if they don't exist.
        Usage: msg.set_nested(html_content, "data", "data", "html")
        """
        if not keys:
            return

        current_level = self.data
        
        # Iterate over all keys except the last one to build the path
        for key in keys[:-1]:
            # If key doesn't exist or isn't a dict, create/overwrite it with an empty dict
            if key not in current_level or not isinstance(current_level[key], dict):
                current_level[key] = {}
            # Move deeper
            current_level = current_level[key]
        
        # Set the value at the final key
        current_level[keys[-1]] = value
