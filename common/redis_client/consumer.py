"""High-level Redis stream consumer wrapper for reliable, ordered message consumption.

This module provides RedisConsumer, a consumer group abstraction that wraps Redis Streams
to handle consumer group management, message acknowledgment, and crash recovery. It enforces
FIFO ordering and ensures message reliability through explicit acknowledgment tracking.
"""

import json
from logging import Logger, getLogger
from typing import Any, Dict, List, Optional

import redis

from common.redis_client.connection import redis_connection


class RedisConsumer:
    """Consumer for Redis Streams with consumer group support.

    Provides a high-level interface to Redis consumer groups for reliable, ordered
    message consumption. Automatically creates consumer groups on first connection and
    handles message acknowledgment, pending message recovery, and JSON decoding.

    Lifecycle:
        1. __init__ creates/joins the consumer group and starts from message ID "0" (all
           existing messages) or ">" (new messages only, depending on configuration).
        2. consume_one/consume_many reads messages marked ">" (new, undelivered messages).
        3. acknowledge_message marks messages as processed in the consumer group.
        4. consume_pending recovers unacknowledged messages on service restart.

    Redis Consumer Group Semantics:
        - Consumer groups track delivery state per message and per consumer.
        - ">" represents new, undelivered messages to the consumer group.
        - Acknowledged (XACK'd) messages are removed from pending entry list (PEL).
        - Unacknowledged messages are tracked and can be recovered after crashes.
    """

    def __init__(self, stream_name: str, group_name: str, consumer_name: str) -> None:
        """Initialize a Redis Stream consumer with consumer group semantics.

        Args:
            stream_name (str): Name of the Redis stream. Must be non-empty.
            group_name (str): Name of the consumer group. Multiple consumers share one group.
            consumer_name (str): Unique identifier for this consumer within the group.

        Raises:
            ValueError: If any argument is empty or not a string.

        Consumer Group Semantics:
            - All consumers in the same group share the same PEL (pending entry list).
            - Each consumer tracks its own unacknowledged messages within the group.
            - Multiple instances with the same consumer_name will be treated as one logical
              consumer; use unique names for parallel processing.
        """

        if not isinstance(stream_name, str) or not stream_name:
            raise ValueError("stream_name must be a non-empty str.")

        if not isinstance(consumer_name, str) or not consumer_name:
            raise ValueError("consumer_name must be a non-empty string.")

        if not isinstance(group_name, str) or not group_name:
            raise ValueError("group_name must be a non-empty string.")

        self.logger: Logger = getLogger(f"{consumer_name}.redis_consumer")
        self.stream_name: str = stream_name
        self.group_name: str = group_name
        self.consumer_name: str = consumer_name
        self.client: redis.Redis = redis_connection.get_client()
        self._create_group()
        self.logger.info(
            f"RedisConsumer ready: stream='{self.stream_name}', group='{self.group_name}'"
        )

    def _create_group(self) -> None:
        """Create consumer group idempotently or skip if already exists.

        Uses Redis XGROUP CREATE with id="0" to ensure the group consumes all existing
        and future messages. Idempotent: subsequent calls are no-ops (BUSYGROUP error ignored).

        Consumer Group Initialization:
            - id="0": Instructs the group to consume from the beginning of the stream.
            - id="$": Would only consume messages after group creation (not used here).
            - mkstream=True: Creates the stream if it doesn't exist.
        """
        try:
            self.client.xgroup_create(
                self.stream_name, self.group_name, id="0", mkstream=True
            )

            self.logger.info(
                f"Created group '{self.group_name}' on stream '{self.stream_name}'."
            )

        except redis.exceptions.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise e
            self.logger.debug(
                f"Group '{self.group_name}' already exists on stream '{self.stream_name}'."
            )

    def _decode_one_message(
        self, stream_name: str, redis_message_id: str, fields: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Decode a raw Redis stream message, parsing JSON payload field.

        Args:
            stream_name: Name of the stream the message came from.
            redis_message_id: Unique Redis message ID (timestamp-sequence).
            fields: Raw field dictionary from Redis (bytes converted by client).

        Returns:
            Dict with keys: stream, redis_message_id, data (parsed JSON payload).
        """
        decoded_fields: Dict[str, Any] = fields
        message_data: Dict[str, Any] = {}

        if "payload" in decoded_fields:
            message_data = json.loads(decoded_fields["payload"])
        else:
            self.logger.warning(
                f"Message {redis_message_id} is missing 'payload' field."
            )
            message_data = decoded_fields

        return {
            "stream": stream_name,
            "redis_message_id": redis_message_id,
            "data": message_data,
        }

    def consume_one(self, block: int = 0) -> Optional[Dict[str, Any]]:
        """Read one undelivered message from the stream for this consumer group.

        Args:
            block (int): Milliseconds to block waiting for a message. 0 = no blocking.

        Returns:
            Dict with stream, redis_message_id, and data; None if timeout/no messages.

        Redis Semantics:
            ">" represents undelivered messages. Consumer group tracks which messages
            have been delivered (pending entry list). Acknowledged messages are removed.
        """
        try:
            response = self.client.xreadgroup(
                self.group_name,
                self.consumer_name,
                streams={self.stream_name: ">"},
                count=1,
                block=block,
            )

            if not response:
                return None

            """
            Example format of response
            [
                ["stream_name_A", (message1, message2, ...)],
                ["stream_name_B", (message1, message2, ...)]
            ]
            """

            stream_name: str
            messages: List[str]

            stream_name, messages = response[0]
            redis_message_id, fields = messages[0]

            return self._decode_one_message(stream_name, redis_message_id, fields)

        except Exception as e:
            self.logger.error(f"Could not consume a single message: {e}")
            raise e

    def consume_many(
        self, num_to_consume: int = 1, block: int = 0
    ) -> Optional[List[Dict[str, Any]]]:
        """Read up to N undelivered messages from the stream for this consumer group.

        Args:
            num_to_consume (int): Maximum number of messages to read.
            block (int): Milliseconds to block. 0 = non-blocking, may return fewer messages.

        Returns:
            List of message dicts, or None if timeout/no messages. Skips decode errors.
        """
        try:
            all_messages: List[Dict[str, Any]] = []

            response = self.client.xreadgroup(
                self.group_name,
                self.consumer_name,
                streams={self.stream_name: ">"},
                count=num_to_consume,
                block=block,
            )

            if not response:
                return None

            for stream_name, messages in response:
                for redis_message_id, fields in messages:
                    try:

                        message_dict: Dict[str, Any] = self._decode_one_message(
                            stream_name, redis_message_id, fields
                        )

                        all_messages.append(message_dict)

                    except json.JSONDecodeError as e:
                        self.logger.error(
                            f"Skipping message {redis_message_id}... Could not decode message from stream '{stream_name}' due to JSON decode error: {e}"
                        )
                        continue

            return all_messages

        except Exception as e:
            self.logger.error(f"Could not consume a many messages: {e}")
            raise e

    def consume_pending(self) -> List[Dict[str, Any]]:
        """Recover unacknowledged messages from the consumer's pending entry list.

        Called on service startup to replay messages that were delivered but not
        acknowledged before a crash. Uses "0-0" to read all pending messages.

        Returns:
            List of pending message dicts for this consumer. Empty list if none.
        """

        try:
            all_messages: List[Dict[str, Any]] = []

            response = self.client.xreadgroup(
                self.group_name,
                self.consumer_name,
                streams={self.stream_name: "0-0"},
            )

            if not response:
                return all_messages

            for stream_name, messages in response:
                for redis_message_id, fields in messages:
                    try:
                        message_dict: Dict[str, Any] = self._decode_one_message(
                            stream_name, redis_message_id, fields
                        )
                        all_messages.append(message_dict)
                    except json.JSONDecodeError as e:
                        self.logger.error(
                            f"Skipping message {redis_message_id}... Could not decode message from stream '{stream_name}' due to JSON decode error: {e}"
                        )
                        continue
            return all_messages

        except Exception as e:
            self.logger.error(f"Could not consume a many messages: {e}")
            raise e

    def acknowledge(self, redis_message_id: str) -> None:
        """Mark a message as processed (remove from pending entry list).

        Args:
            redis_message_id: The Redis message ID to acknowledge via XACK.

        Raises:
            Exception: If XACK fails or ACK count is 0 (message not pending).

        Semantics:
            XACK removes the message from the consumer group's pending list. This allows
            the message to be deleted and prevents it from being redelivered on crashes.
        """

        try:
            result = self.client.xack(
                self.stream_name, self.group_name, redis_message_id
            )
            if result == 0:
                raise Exception("Failed to ack")
            self.client.hincrby(
                f"stream:{self.stream_name}:group:{self.group_name}:acks",
                self.consumer_name,
                1,
            )
            self.logger.debug(f"Successfully acknowledged {redis_message_id}")

        except Exception as e:
            self.logger.error(
                f"Failed to acknowledging message {redis_message_id} on stream {self.stream_name}: {e}"
            )
            raise e

    def acknowledge_and_delete(self, stream_name: str, redis_message_id: str) -> None:
        """Acknowledge a message and permanently delete it from the stream.

        Args:
            stream_name: The stream to delete from.
            redis_message_id: The message ID to ack and delete.

        Raises:
            Exception: If XACK or XDEL fails.

        Semantics:
            XACK removes from pending list; XDEL physically removes the message entry
            to free memory. Use after successfully processing the message.
        """

        try:
            ack_result = self.client.xack(
                stream_name, self.group_name, redis_message_id
            )
            if ack_result == 0:
                raise Exception("Failed to ack")
            self.client.hincrby(
                f"stream:{self.stream_name}:group:{self.group_name}:acks",
                self.consumer_name,
                1,
            )
            del_result = self.client.xdel(stream_name, redis_message_id)
            if del_result == 0:
                raise Exception("Failed to del")

            self.logger.debug(
                f"Successfully acknowledged and cleaned up {redis_message_id}"
            )
        except Exception as e:
            self.logger.error(
                f"Failed to acknowledging message {redis_message_id} on stream {stream_name}: {e}"
            )
            raise e
