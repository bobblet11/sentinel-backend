import json
from logging import Logger, getLogger
from typing import Any, Dict, List, Optional

import redis

from common.redis_client.connection import redis_connection


class RedisConsumerCombiner:
    """
    A higher-level consumer that fetches messages from multiple Redis streams
    in a single, efficient operation.

    It listens to all specified streams simultaneously and returns messages
    from whichever stream has them available first.
    """

    def __init__(self, streams: List[str], group_name: str, consumer_name: str) -> None:
        """
        Initializes the RedisConsumerCombiner.
        """

        if not isinstance(streams, list) or not streams:
            raise ValueError("streams must be a non-empty list.")

        if not isinstance(consumer_name, str) or not consumer_name:
            raise ValueError("consumer_name must be a non-empty string.")

        if not isinstance(group_name, str) or not group_name:
            raise ValueError("group_name must be a non-empty string.")

        self.logger: Logger = getLogger(f"{consumer_name}.redis_consumer_combiner")
        self.streams: List[str] = streams
        self.group_name: str = group_name
        self.consumer_name: str = consumer_name
        self.client: redis.Redis = redis_connection.get_client()
        self._create_groups()
        self.logger.info(
            f"RedisConsumerCombiner ready: streams={self.streams}, group='{self.group_name}'"
        )

    def _create_groups(self) -> None:
        """
        Idempotently creates the consumer group on all streams.
        """

        for stream in self.streams:
            try:
                # Use '0' to read the entire history if the group is new,
                # or '$' to only get new messages. '0' is often safer for dev.
                self.client.xgroup_create(
                    stream, self.group_name, id="0", mkstream=True
                )
                self.logger.info(
                    f"Created group '{self.group_name}' on stream '{stream}'."
                )

            except redis.exceptions.ResponseError as e:
                if "BUSYGROUP" not in str(e):
                    raise e
                self.logger.debug(
                    f"Group '{self.group_name}' already exists on stream '{stream}'."
                )

    def _decode_one_message(
        self, stream_name: str, redis_message_id: str, fields: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Decodes a single raw message from Redis, handling byte conversion and JSON parsing.
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
        """
        Waits for and consumes ONE message from ANY of the configured streams.

        In Redis cluster mode, multi-stream XREADGROUP across different stream
        keys can fail with a cross-slot error, so we probe one stream at a time.
        """
        try:
            for stream_name in self.streams:
                response = self.client.xreadgroup(
                    self.group_name,
                    self.consumer_name,
                    streams={stream_name: ">"},
                    count=1,
                    block=block,
                )

                if not response:
                    continue

                _, messages = response[0]
                if not messages:
                    continue

                redis_message_id, fields = messages[0]

                return self._decode_one_message(stream_name, redis_message_id, fields)

            return None

        except Exception as e:
            self.logger.error(f"Could not consume a single message: {e}")
            raise e

    def consume_many(
        self, num_to_consume: int = 1, block: int = 0
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Waits for and consumes up to N messages from ANY of the configured streams.

        To stay compatible with Redis cluster mode, each stream is read
        individually instead of issuing a single multi-stream XREADGROUP.
        """

        try:
            for stream_name in self.streams:
                all_messages: List[Dict[str, Any]] = []

                response = self.client.xreadgroup(
                    self.group_name,
                    self.consumer_name,
                    streams={stream_name: ">"},
                    count=num_to_consume,
                    block=block,
                )

                if not response:
                    continue

                _, messages = response[0]
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

                if all_messages:
                    return all_messages

            return []

        except Exception as e:
            self.logger.error(f"Could not consume a many messages: {e}")
            raise e

    def consume_pending(self) -> Optional[List[Dict[str, Any]]]:
        """
        Consumes messages that are pending for this specific consumer.
        This should be called on startup to recover from a previous crash.
        """

        try:
            all_messages: List[Dict[str, Any]] = []

            for stream_name in self.streams:
                response = self.client.xreadgroup(
                    self.group_name,
                    self.consumer_name,
                    streams={stream_name: "0-0"},
                )

                if not response:
                    continue

                _, messages = response[0]
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

    def acknowledge(self, stream_name: str, redis_message_id: str) -> None:
        """
        Acknowledges that a message from a specific stream has been processed.
        """

        try:
            result = self.client.xack(stream_name, self.group_name, redis_message_id)
            if result == 0:
                raise Exception("Failed to ack")

            self.client.hincrby(
                f"stream:{stream_name}:group:{self.group_name}:acks",
                self.consumer_name,
                1,
            )
            self.logger.debug(f"Successfully acknowledged {redis_message_id}")
        except Exception as e:
            self.logger.error(
                f"Failed to acknowledging message {redis_message_id} on stream {stream_name}: {e}"
            )
            raise e

    def acknowledge_and_delete(self, stream_name: str, redis_message_id: str) -> None:
        """
        Acknowledges that a message from a specific stream has been processed and deletes it from last stream
        """

        try:
            ack_result = self.client.xack(
                stream_name, self.group_name, redis_message_id
            )
            if ack_result == 0:
                raise Exception("Failed to ack")
            self.client.hincrby(
                f"stream:{stream_name}:group:{self.group_name}:acks",
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
