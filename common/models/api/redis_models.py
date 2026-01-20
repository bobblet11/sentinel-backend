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
    job_uid: int
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
    
    

class Message(BaseModel):
    """
    Represents the actual message data type passed through a message queue
    """
    header: MessageHeader
    data: Union[MessagePayload] 
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
        return self.data.data.article_url

    @property
    def html(self) -> Optional[str]:
        return self.data.data.raw_html
    
    @property
    def text(self) -> Optional[str]:
        return self.data.data.parsed_text

    
    def set_raw_html(self, page_html: str) -> None:
        self.data.data.raw_html = page_html
    
    def set_parsed_text(self, parsed_text: str) -> None:
        self.data.data.parsed_text = parsed_text
    
    def add_timestamp(self, stage_name: JobStage) -> None:
        
        timestamp_row = MessageTimestamp(
            job_uid = self.data.header.uid,
            stage_name = stage_name,
            timestamp = datetime.datetime.now().isoformat()
        )
        
        self.data.stage_timestamps.append(timestamp_row)
