from typing import Any, Union

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
