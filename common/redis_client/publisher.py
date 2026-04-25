import json
from logging import Logger, getLogger
from typing import Any, Dict, List

import redis

from common.redis_client.connection import redis_connection


class RedisPublisher:
    """
    A high-level, reliable wrapper for Redis stream-based FIFO queues.
    """

    def __init__(self, stream_name: str):
        """
        Args:
        stream_name (str): The name of the Redis stream to publish to.
        """

        if not isinstance(stream_name, str) or not stream_name:
            raise ValueError("Stream name must be a non-empty string.")
        
        self.logger: Logger = getLogger(f"{stream_name}.redis_publisher")
        self.stream_name:str = stream_name
        self.max_len:int = 100_000
        self.client:redis.Redis = redis_connection.get_client()

    def publish_one(self, message_payload: Dict[Any, Any]) -> str:
        """
        Serializes a dictionary to JSON and adds it to the stream.

        Args:
                message: a message object that has been deserialised into a dictionary, that is waiting to be published

        Returns:
                str: The unique message ID if successful, otherwise None.
        """
        if not message_payload:
            raise Exception("No message to publish")

        payload:Dict[str, Any] = {"payload": json.dumps(message_payload)}
        redis_message_id:str = self.client.xadd(
            self.stream_name, payload, maxlen=self.max_len, approximate=True
        )
        self.logger.debug(f"Published message under id {redis_message_id} to {self.stream_name}")
        return redis_message_id


    def publish_many(self, messages: List[Dict[Any, Any]]) -> List[str]:
        """
        Serializes messages dictionaries to JSON and adds all to the stream.

        Args:
                messages: A list of JSON-serializable dictionaries, where each
                        dictionary represents a message to be published.
        Returns:
                A list of the unique Redis message IDs for the published messages
                if successful, otherwise None.
        """
        
        if not messages or len(messages) == 0:
            raise Exception("No messages to publish")

        pipe = self.client.pipeline(transaction=True)

        for message_data in messages:
            payload:Dict[str,Any] = {"payload": json.dumps(message_data)}
            pipe.xadd(
                self.stream_name, payload, maxlen=self.max_len, approximate=True
            )
        redis_message_ids:List[str] = pipe.execute()

        self.logger.debug(f"Published {len(redis_message_ids)} messages to {self.stream_name}.")
        return redis_message_ids
