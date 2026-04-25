"""Prioritized Redis stream consumer combining multiple streams with priority weighting.

This module handles consumption from multiple Redis streams with configurable priority levels.
The consumer uses a blocking read strategy where higher-priority streams (user jobs) are checked
before lower-priority streams (background jobs), ensuring user-submitted work is processed
before batch/ingestor jobs.

Key features:
    - Reads from multiple streams in priority order
    - Configurable blocking times per stream based on priority level
    - Supports exponential, linear, and uniform priority weighting strategies
    - Handles stream message acknowledgment and deletion
    - Recovers pending messages on startup
"""

import json
from enum import StrEnum
from logging import Logger, getLogger
from typing import Any, Dict, List, Optional

import redis

from common.redis_client.connection import redis_connection

DEFAULT_BLOCK_MS = 5_000
MIN_BLOCK_MS = 1_000


class BlockPrioritisationLevel(StrEnum):
    """Enum defining how blocking times are calculated for priority streams.

    Priority levels determine the timeout (block) duration for checking each stream:
    - USER streams (e.g., user:to.be.nlp) are checked first with shorter timeouts
    - BACKGROUND streams (e.g., background:to.be.nlp) are checked later with longer timeouts

    Attributes:
        EXPONENTIAL: Block times increase exponentially with priority rank.
            Lower-priority streams wait 2^n times longer. Strongly favors high-priority work.
        LINEAR: Block times increase linearly (2000ms per rank). Balances fairness and priority.
        UNIFORM_5: All streams block for 5000ms. Fair round-robin, minimal priority bias.
    """

    EXPONENTIAL = "exponential"
    LINEAR = "linear"
    UNIFORM_5 = "uniform_5"


class PrioritisedRedisConsumerCombiner:
    """Consumes messages from multiple Redis streams with configurable priority weighting.

    This consumer reads from multiple streams in a prioritized order. Each stream is checked
    sequentially using a blocking read with a stream-specific timeout. This ensures that
    higher-priority streams (e.g., user jobs) are always serviced before lower-priority
    streams (e.g., background jobs), while still eventually processing all work.

    Priority is determined by mapping each stream to an integer rank (lower rank = higher
    priority). Streams are checked in ascending order by rank.

    Block times are calculated based on the BlockPrioritisationLevel strategy:
        - EXPONENTIAL: Lower-priority streams block longer, strongly favoring high-priority work
        - LINEAR: Predictable fairness with steady priority bias
        - UNIFORM_5: All streams block equally, fair round-robin behavior

    Example:
        >>> streams = ['user:to.be.nlp', 'background:to.be.nlp']
        >>> priority_map = {'user:to.be.nlp': 1, 'background:to.be.nlp': 2}
        >>> block_map = {'user:to.be.nlp': 1000, 'background:to.be.nlp': 5000}
        >>> consumer = PrioritisedRedisConsumerCombiner(block_map, 'nlp_group', 'worker1', priority_map)
        >>> msg = consumer.consume_one()  # Checks user stream first (1000ms), then background (5000ms)
    """

    def __init__(
        self,
        stream_to_block_map: Optional[Dict[str, int]],
        group_name: str,
        consumer_name: str,
        stream_to_priority_map: Dict[str, int],
    ) -> None:
        """Initializes the PrioritisedRedisConsumerCombiner.

        Args:
            stream_to_block_map: Optional dict mapping stream names to block durations (ms).
                If None, defaults to DEFAULT_BLOCK_MS for all streams. Values < MIN_BLOCK_MS
                are automatically set to DEFAULT_BLOCK_MS.
            group_name: Consumer group name for Redis stream consumption. Used for tracking
                message acknowledgments and coordinating multiple consumers.
            consumer_name: Unique consumer identifier within the group. Used for pending
                message recovery on startup.
            stream_to_priority_map: Dict mapping stream names to priority ranks (int).
                Lower rank = higher priority. Must be non-empty and all streams in
                stream_to_block_map must also appear here.

        Raises:
            ValueError: If stream_to_priority_map is empty, consumer_name or group_name
                is empty, or if streams don't match between priority and block maps.
        """

        if not isinstance(stream_to_priority_map, dict) or not stream_to_priority_map:
            raise ValueError("stream_to_priority_map must be a non-empty dict.")

        if not isinstance(consumer_name, str) or not consumer_name:
            raise ValueError("consumer_name must be a non-empty string.")

        if not isinstance(group_name, str) or not group_name:
            raise ValueError("group_name must be a non-empty string.")

        if not stream_to_block_map:
            stream_to_block_map = {
                stream_name: DEFAULT_BLOCK_MS
                for stream_name in stream_to_priority_map.keys()
            }
        else:
            stream_to_block_map = {
                stream_name: (block if block >= MIN_BLOCK_MS else DEFAULT_BLOCK_MS)
                for stream_name, block in stream_to_block_map.items()
            }

        if set(stream_to_priority_map.keys()) != set(stream_to_block_map.keys()):
            raise ValueError(
                "stream_to_priority_map and stream_to_block_map must match."
            )

        self.logger: Logger = getLogger(f"{consumer_name}.redis_consumer_combiner")
        self.stream_to_priority_map: Dict[str, int] = stream_to_priority_map
        self.stream_to_block_map: Dict[str, int] = stream_to_block_map
        self.group_name: str = group_name
        self.consumer_name: str = consumer_name
        self.client: redis.Redis = redis_connection.get_client()
        self._create_groups()
        self.logger.info(
            f"PrioritisedConsumerCombiner ready: streams={list(self.stream_to_priority_map.keys())}, group='{self.group_name}'"
        )

    def _create_groups(self) -> None:
        """Idempotently creates consumer groups on all configured streams.

        Creates a Redis consumer group for each stream if it does not already exist.
        Uses '0' as the starting ID to read the entire stream history for new groups.
        Subsequent runs detect existing groups (BUSYGROUP error) and skip creation.

        Raises:
            redis.exceptions.ResponseError: For errors other than BUSYGROUP.
        """
        streams: List[str] = self.stream_to_priority_map.keys()
        for stream in streams:
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
        """Decodes a single raw Redis stream message into a structured format.

        Extracts and parses the JSON 'payload' field from the Redis message fields dict,
        handling byte conversion and missing payload gracefully. Returns a standardized
        dict with stream metadata and decoded data.

        Args:
            stream_name: Name of the source stream.
            redis_message_id: Redis-generated message ID (e.g., '1234567890-0').
            fields: Raw fields dict from Redis XREAD response.

        Returns:
            Dict with keys:
                - 'stream': Source stream name
                - 'redis_message_id': Message ID for acknowledgment
                - 'data': Parsed JSON payload (or raw fields if payload missing)
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

    def consume_one(self) -> Optional[Dict[str, Any]]:
        """Waits for and consumes ONE message from configured streams in priority order.

        Checks each stream in ascending priority rank order (lowest rank first).
        For each stream, performs a blocking read with the stream's configured timeout.
        Returns the first message found from any stream, prioritizing higher-ranked streams.

        If a higher-priority stream has messages, lower-priority streams are not checked
        in that cycle. This ensures user jobs (typically priority 1) are processed before
        background jobs (typically priority 2).

        Returns:
            A single decoded message dict (see _decode_one_message), or None if all
            streams timeout without messages.

        Raises:
            Exception: If Redis operation fails.
        """
        try:
            for stream_name in sorted(
                self.stream_to_priority_map, key=self.stream_to_priority_map.get
            ):
                response = self.client.xreadgroup(
                    self.group_name,
                    self.consumer_name,
                    streams={stream_name: ">"},
                    count=1,
                    block=self.stream_to_block_map[stream_name],
                )

                if not response:
                    # just go to the next priority level if no messages arrive
                    continue

                messages: List[str]
                stream_name, messages = response[0]
                redis_message_id, fields = messages[0]

                return self._decode_one_message(stream_name, redis_message_id, fields)

        except Exception as e:
            self.logger.error(f"Could not consume a single message: {e}")
            raise e

    def consume_many(self, num_to_consume: int = 1) -> Optional[List[Dict[str, Any]]]:
        """Waits for and consumes up to N messages from configured streams in priority order.

        Similar to consume_one, but retrieves up to num_to_consume messages from the first
        non-empty stream in priority order. Does not mix messages from different streams
        in a single call.

        Args:
            num_to_consume: Maximum number of messages to retrieve from a stream.
                Defaults to 1.

        Returns:
            A list of decoded message dicts (see _decode_one_message) from the first
            stream with available messages, or None if all streams timeout.

        Raises:
            Exception: If Redis operation fails.
        """

        try:
            for stream_name in sorted(
                self.stream_to_priority_map, key=self.stream_to_priority_map.get
            ):
                response = self.client.xreadgroup(
                    self.group_name,
                    self.consumer_name,
                    streams={stream_name: ">"},
                    count=num_to_consume,
                    block=self.stream_to_block_map[stream_name],
                )

                if not response:
                    # just go to the next priority level if no messages arrive
                    continue

                stream_name, messages = response[0]

                if not messages:
                    # just go to the next priority level if no messages arrive
                    continue

                messages = [
                    self._decode_one_message(stream_name, redis_message_id, fields)
                    for redis_message_id, fields in messages
                ]
                return messages
            return None
        except Exception as e:
            self.logger.error(f"Could not consume a any messages: {e}")
            raise e

    def consume_pending(self) -> Optional[List[Dict[str, Any]]]:
        """Consumes messages pending for this specific consumer, in priority order.

        Called during startup to recover unacknowledged messages from a previous crash.
        Reads pending entries (ID range '0-0') from each stream in priority order.

        Note: Redis Cluster mode does not allow multi-stream XREADGROUP when streams
        map to different hash slots, so we read one stream at a time.

        Returns:
            A combined list of all pending decoded messages across all streams,
            or an empty list if no pending messages exist.

        Raises:
            Exception: If Redis operation fails.
        """

        try:
            all_messages: List[Dict[str, Any]] = []

            for stream_name in sorted(
                self.stream_to_priority_map, key=self.stream_to_priority_map.get
            ):
                response = self.client.xreadgroup(
                    self.group_name,
                    self.consumer_name,
                    streams={stream_name: "0-0"},
                )

                if not response:
                    continue

                _, messages = response[0]
                for redis_message_id, fields in messages:
                    message_dict: Dict[str, Any] = self._decode_one_message(
                        stream_name, redis_message_id, fields
                    )
                    all_messages.append(message_dict)

            return all_messages

        except Exception as e:
            self.logger.error(f"Could not consume a many messages: {e}")
            raise e

    def acknowledge(self, stream_name: str, redis_message_id: str) -> None:
        """Acknowledges that a message has been successfully processed.

        Marks the message in the consumer group's pending entry list (PEL) as acknowledged
        using XACK. This prevents the message from being redelivered to other consumers.
        Also increments a counter for telemetry.

        Args:
            stream_name: Name of the stream containing the message.
            redis_message_id: Message ID to acknowledge (e.g., '1234567890-0').

        Raises:
            Exception: If acknowledgment fails.
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
        """Acknowledges a message and removes it from the stream.

        Atomically acknowledges (XACK) and deletes (XDEL) the message. Use this for
        final cleanup of processed messages, especially for the last stage in the pipeline
        where messages no longer need to be retained.

        Args:
            stream_name: Name of the stream containing the message.
            redis_message_id: Message ID to acknowledge and delete.

        Raises:
            Exception: If acknowledgment or deletion fails.
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

    @staticmethod
    def generate_stream_to_priority_mapping(input_streams: List[str]):
        """Generates a priority map from a list of streams in order.

        Assumes input streams are ordered from highest to lowest priority.
        Assigns rank 1 to the first stream, 2 to the second, etc.

        Args:
            input_streams: Ordered list of stream names. First = highest priority.

        Returns:
            Dict mapping stream name to priority rank (int, 1-indexed).

        Raises:
            ValueError: If input_streams is empty.
        """
        if not input_streams:
            raise ValueError("Missing input_streams")

        mapping = {}
        for i in range(len(input_streams)):
            mapping[input_streams[i]] = i + 1
        return mapping

    @staticmethod
    def generate_stream_to_block_mapping(
        input_streams: List[str],
        level: BlockPrioritisationLevel = BlockPrioritisationLevel.LINEAR,
        minimum_block_ms: int = MIN_BLOCK_MS,
    ):
        """Generates blocking timeouts per stream based on priority and strategy.

        Creates a map of stream names to block durations (ms) using the specified
        BlockPrioritisationLevel strategy. Lower-priority streams receive longer
        timeouts, ensuring higher-priority streams are checked more frequently.

        Strategy behavior (for stream order [0] > [1] > [2]):
            EXPONENTIAL: [1000, 2000, 4000] - exponential increase favors high-priority
            LINEAR: [1000, 3000, 5000] - predictable, configurable fairness
            UNIFORM_5: [5000, 5000, 5000] - fair round-robin, minimal bias

        Args:
            input_streams: Ordered list of stream names (highest to lowest priority).
            level: BlockPrioritisationLevel strategy. Defaults to LINEAR.
            minimum_block_ms: Base timeout in ms. Defaults to MIN_BLOCK_MS (1000).

        Returns:
            Dict mapping stream name to block duration (int, milliseconds).

        Raises:
            ValueError: If input_streams is empty or level is invalid.
        """
        if not input_streams:
            raise ValueError("Missing input_streams")

        mapping = {}

        LINEAR_GRADIENT = 2000
        EXPONENTIAL_BASE = 2
        input_streams_length = len(input_streams)
        for priority_index, stream_name in enumerate(input_streams):
            inverse_priority_index = (input_streams_length - 1) - priority_index

            if level is BlockPrioritisationLevel.LINEAR:
                mapping[stream_name] = minimum_block_ms + (
                    LINEAR_GRADIENT * inverse_priority_index
                )

            elif level is BlockPrioritisationLevel.EXPONENTIAL:
                mapping[stream_name] = minimum_block_ms * (
                    EXPONENTIAL_BASE**inverse_priority_index
                )

            elif level is BlockPrioritisationLevel.UNIFORM_5:
                mapping[stream_name] = 5_000

            else:
                raise ValueError(f"Invalid prioritisation level provided: {level}")
        return mapping
