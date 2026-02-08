import json
from typing import Any, Dict, List, Optional
from logging import Logger, getLogger
from common.redis_client.connection import redis_connection
import redis

class RedisPublisherMock:
    """
    A high-level, reliable wrapper for Redis stream-based FIFO queues.
    """

    def __init__(self):

        self.logger: Logger = getLogger("mock.redis_publisher")
        self.logger.info("--- Initializing RedisPublisher ---")
        self.queue = []
        self.logger.info(f"--- Initialized RedisPublisher ---")

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
        self.queue.append(payload)
        redis_message_id:str = len(self.queue) - 1
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

        lower_id = len(self.queue) - 1
        upper_id = lower_id + len(messages)
        self.queue.extend(messages)
        redis_message_ids = list(range(lower_id, upper_id))

        self.logger.debug(f"Published {len(redis_message_ids)} messages to {self.stream_name}.")
        return redis_message_ids
