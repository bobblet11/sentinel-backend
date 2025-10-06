# from pydantic import BaseModel
# from typing import Dict, Any

# class MessageHeader(BaseModel):
#         """
#         Represents the basic information used to identify and get stats on Messages
#         """
#         message_id: str
#         timestamp: str

# class MessageURLPayload(BaseModel):
#         """
#         Represents the payload between ingestor and web scraper service
#         """
#         url:str
#         source_rss: str
        
# class Message(BaseModel):
#         """
#         Represents the actual message data type passed through a message queue
#         """
#         header: MessageHeader
#         dataType: str
#         from typing import Union, Any
#         data: Union[MessageURLPayload, Any]
                

from typing import Union, Any
from pydantic import BaseModel
from datetime import datetime

class MessageHeader(BaseModel):
    message_id: str
    timestamp: str

class MessageURLPayload(BaseModel):
    url: str
    source_rss: str

class Message(BaseModel):
    header: MessageHeader
    data: Union[MessageURLPayload, Any]  # Fixed for Python 3.9