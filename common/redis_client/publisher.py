"""High-level Redis stream publisher for ordered, reliable message delivery.

This module provides RedisPublisher, a publisher wrapper that encapsulates the details
of stream naming conventions, JSON serialization, and batch operations for publishing
messages to Redis Streams. Ensures FIFO ordering and memory-bounded stream length.
"""

import json
from logging import Logger, getLogger
from typing import Any, Dict, List

import redis

from common.redis_client.connection import redis_connection


class RedisPublisher:
    """Publisher for adding messages to Redis Streams.

    Provides a high-level interface for publishing JSON-serialized messages to Redis Streams
    with automatic memory management (bounded stream length via MAXLEN) and batch
    operations via pipelining.

    Stream Naming Conventions:
        - Active streams: "{job_type}:to.be.{stage}"
          Examples: user:to.be.scraped, background:to.be.nlp
        - Failure streams: "{job_type}:failed.{stage}"
        - job_type is "user" or "background" (priority lanes)
        - stage is the processing stage (scraped, nlp, retrieval, etc.)

    Message Format:
        Messages are stored as {"payload": "<JSON string>"}. The JSON-serialized
        message data is wrapped in a "payload" field for consistency with the consumer.
    """

    def __init__(self, stream_name: str):
        """Initialize a Redis Stream publisher.

        Args:
            stream_name (str): Name of the target Redis stream. Use naming convention:
                "{job_type}:to.be.{stage}" for consistency.

        Raises:
            ValueError: If stream_name is empty or not a string.

        Example:
            publisher = RedisPublisher("user:to.be.scraped")
        """

        if not isinstance(stream_name, str) or not stream_name:
            raise ValueError("Stream name must be a non-empty string.")

        self.logger: Logger = getLogger(f"{stream_name}.redis_publisher")
        self.stream_name: str = stream_name
        self.max_len: int = 100_000
        self.client: redis.Redis = redis_connection.get_client()

    def publish_one(self, message_payload: Dict[Any, Any]) -> str:
        """Serialize and publish a single message to the stream.

        Args:
            message_payload: Dictionary to JSON-serialize and publish.

        Returns:
            str: Unique Redis message ID (e.g., "1692345600000-0").

        Raises:
            Exception: If message_payload is empty/None.

        Ordering:
            Messages are assigned monotonically increasing IDs by Redis, guaranteeing
            stream order and FIFO consumption by consumer groups.
        """
        if not message_payload:
            raise Exception("No message to publish")

        payload: Dict[str, Any] = {"payload": json.dumps(message_payload)}
        redis_message_id: str = self.client.xadd(
            self.stream_name, payload, maxlen=self.max_len, approximate=True
        )
        self.logger.debug(
            f"Published message under id {redis_message_id} to {self.stream_name}"
        )
        return redis_message_id

    def publish_many(self, messages: List[Dict[Any, Any]]) -> List[str]:
        """Serialize and publish multiple messages to the stream via pipelining.

        Args:
            messages: List of dictionaries to JSON-serialize and publish.

        Returns:
            List of Redis message IDs for each published message, in order.

        Raises:
            Exception: If messages list is empty or None.

        Semantics:
            Uses a Redis pipeline (transaction=True) to batch operations, reducing
            round-trip latency. Messages are ordered by their position in the list.
        """

        if not messages or len(messages) == 0:
            raise Exception("No messages to publish")

        pipe = self.client.pipeline(transaction=True)

        for message_data in messages:
            payload: Dict[str, Any] = {"payload": json.dumps(message_data)}
            pipe.xadd(self.stream_name, payload, maxlen=self.max_len, approximate=True)
        redis_message_ids: List[str] = pipe.execute()

        self.logger.debug(
            f"Published {len(redis_message_ids)} messages to {self.stream_name}."
        )
        return redis_message_ids
