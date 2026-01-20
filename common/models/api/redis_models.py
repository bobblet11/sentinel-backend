import datetime
from typing import Any, List, Union, Dict, Optional
from dataclasses import dataclass
from pydantic import BaseModel

from common.models.api.dtos.job import JobStage


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

#redis message wraps a message/job object

class MessageTimestamp(BaseModel):
    """
    Represents the timestamp of a stage
    """
    job_uid: str
    stage_name: str
    timestamp: str
class MessageHeader(BaseModel):
    """
    Represents the basic information used to identify and get stats on Messages
    """

    id: int | None = None
    uid: str
    type: str
    status: str
    created_at: str


class MessagePayload(BaseModel):
    """
    Represents the payload between ingestor and web scraper service
    """
    #initial request
    article_url: str    | None     = None
    #ingestion
    news_outlet: str    | None     = None
    title: str          | None     = None
    publish_date: str   | None     = None
    author: str         | None     = None
    summary: str        | None     = None
    #scrape
    raw_html: str       | None     = None
    parsed_text: str    | None     = None
    
    #nlp
    
    
@dataclass
class ParseResult:
    text: str
    title: Optional[str]
    author: Optional[str]
    published_at: Optional[str]
    
    def __getitem__(self, key):
        return getattr(self, key, None)
    
    def __setitem__(self, key, value):
        if hasattr(self, key):
            setattr(self, key, value)
        else:
            raise KeyError(f"{key} is not a valid field")
        

class Message(BaseModel):
    """
    Represents the actual message data type passed through a message queue
    """
    header: MessageHeader
    payload: MessagePayload
    stage_timestamps: List[MessageTimestamp]

@dataclass
class StreamMessage:
    # following fields are used for redis management
    stream: str
    redis_id: str
    priority: Union[int, float]
    
    # following field are the actual job keys
    data: Message # the actual message object, i.e the class above


    @property
    def type(self) -> Optional[str]:
        return self.data.header.type
    
    @property
    def link(self) -> Optional[str]:
        return self.data.payload.article_url

    @property
    def html(self) -> Optional[str]:
        return self.data.payload.raw_html
    
    @property
    def text(self) -> Optional[str]:
        return self.data.payload.parsed_text

    
    def set_raw_html(self, page_html: str) -> None:
        self.data.payload.raw_html = page_html
    
    def set_parsed_result(self, parsed_result: ParseResult) -> None:
        """Unpacks a ParseResult object and updates the message payload."""
        # Use dot notation on the ParseResult object for clarity and safety
        if not self.data.payload.parsed_text and parsed_result.text:
            self.data.payload.parsed_text = parsed_result.text
            
        if not self.data.payload.title and parsed_result.title:
            self.data.payload.title = parsed_result.title
            
        if not self.data.payload.author and parsed_result.author:
            self.data.payload.author = parsed_result.author
            
        if not self.data.payload.publish_date and parsed_result.published_at:
            self.data.payload.publish_date = parsed_result.published_at
            
    def add_timestamp(self, stage_name: JobStage) -> None:
        
        timestamp_row = MessageTimestamp(
            job_uid = self.data.header.uid,
            stage_name = stage_name.value,
            timestamp = datetime.datetime.now().isoformat()
        )
        
        self.data.stage_timestamps.append(timestamp_row)
