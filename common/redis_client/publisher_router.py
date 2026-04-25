"""Router for publishing messages to multiple output streams based on routing keys.

This module provides message routing logic that forwards messages to different Redis
streams based on a configurable routing key within the message. This is used to
separate user-submitted jobs from background/ingestor jobs into different processing
queues.

Key features:
    - Inspects message content to determine destination stream
    - Routes user and background jobs to separate stream families
    - Supports batch publishing with grouping by destination
    - Lazy initializes publishers for each destination stream

Example:
    User jobs route to 'user:to.be.nlp'; background jobs to 'background:to.be.nlp'
    based on the 'job_type' field in the message payload.
"""

import hashlib
from logging import Logger, getLogger
from typing import Any, Dict, List

from common.redis_client.publisher import RedisPublisher


def get_nested_value(d: Dict, keys: List[str]) -> Any:
    """Safely retrieves a value from a nested dictionary."""
    for key in keys:
        if not isinstance(d, dict) or key not in d:
            return None
        d = d.get(key)
    return d


class RedisPublisherRouter:
    """Routes messages to different Redis streams based on message content.

    This router acts as a multiplexer, forwarding messages to different output streams
    determined by inspecting a configurable routing key within each message payload.

    Use cases:
        - Separate user (high-priority) jobs from background (low-priority) jobs
        - Route to pipeline stages based on job type or processing context
        - Implement priority-based job queue separation

    Routing logic:
        1. Extract the routing key value from the message (e.g., 'job_type' -> 'user')
        2. Look up the destination stream in the routing map (e.g., 'user' -> 'user:to.be.nlp')
        3. Use the appropriate publisher to send the message to that stream

    Example:
        >>> routing_map = {'user': 'user:to.be.nlp', 'background': 'background:to.be.nlp'}
        >>> router = RedisPublisherRouter(routing_map, ['job_type'])
        >>> router.publish_one({'job_type': 'user', 'data': {...}})
        >>> # Message published to 'user:to.be.nlp'
    """

    def __init__(self, routing_map: Dict[str, str], routing_key: List[str]):
        """Initializes the RedisPublisherRouter with routing rules.

        Args:
            routing_map: Dict mapping routing values to destination stream names.
                Key: routing value (e.g., 'user', 'background')
                Value: destination Redis stream name (e.g., 'user:to.be.nlp')
            routing_key: List of nested keys to extract routing value from message.
                For flat messages: ['job_type']
                For nested: ['metadata', 'job_type']

        Raises:
            ValueError: If routing_map or routing_key is empty.
        """

        if not isinstance(routing_map, dict) or not routing_map:
            raise ValueError("routing_map must be a non-empty dictionary.")

        if not isinstance(routing_key, list) or not routing_key:
            raise ValueError("routing_key must be a non-empty list of strings.")

        unique_handle: str = hashlib.md5(str(routing_map).encode("utf-8")).hexdigest()[
            :5
        ]
        self.logger: Logger = getLogger(f"{unique_handle}.redis_publisher_router")
        self.routing_map: Dict[str, str] = routing_map
        self.routing_key: List[str] = routing_key
        self.publishers: Dict[str, RedisPublisher] = {}

        for message_type, stream_name in self.routing_map.items():
            self.publishers[message_type] = RedisPublisher(stream_name)

        self.logger.info(f"PublisherRouter ready: {routing_map}")

    def _get_nested_value(self, payload: Dict[str, Any], keys: List[str]) -> Any:
        """Extracts a value from nested dictionary using a list of keys.

        Navigates through nested dicts using the provided key path. Raises an exception
        if any intermediate key is missing or the traversal path is invalid.

        Args:
            payload: Dict to traverse.
            keys: List of keys representing the path to the target value.

        Returns:
            The value at the end of the key path.

        Raises:
            Exception: If missing arguments, key not found, or intermediate value is not a dict.
        """
        if not keys or not payload:
            raise Exception("Missing arguments")

        current_level = payload

        for key in keys[:-1]:
            if key not in current_level or not isinstance(current_level[key], dict):
                raise Exception("Key does not exist in payload!")

            current_level: Dict[str, Any] = current_level[key]

        value: Any = current_level[keys[-1]]
        return value

    def publish_one(self, message_payload: Dict[str, Any]) -> str:
        """Routes and publishes a single message to the appropriate stream.

        Extracts the routing value from the message using routing_key, looks up the
        destination stream in the routing map, and publishes to that stream.

        Args:
            message_payload: Message dict to route and publish. Must contain
                the nested keys specified in routing_key.

        Returns:
            The unique Redis message ID (e.g., '1234567890-0').

        Raises:
            Exception: If routing key not found, no publisher configured for routing value,
                or publishing fails.
        """

        # 1. Determine the route
        routing_value: str = self._get_nested_value(message_payload, self.routing_key)
        if not routing_value:
            raise Exception(
                f"Routing key '{self.routing_key}' not found in message. Message not published."
            )

        # 2. Find the correct publisher for that route
        publisher: RedisPublisher = self.publishers.get(routing_value, None)
        if publisher is None:
            raise Exception(
                f"No publisher configured for routing value '{routing_value}'. Message not published."
            )

        # 3. Use the dedicated publisher to send the message
        self.logger.debug(
            f"Routing message of routing value '{routing_value}' to stream '{publisher.stream_name}'."
        )
        # can release exception if fails
        return publisher.publish_one(message_payload)

    def publish_many(self, message_payloads: List[Dict[str, Any]]) -> Dict[str, int]:
        """Routes and batch-publishes multiple messages to their respective streams.

        Groups messages by routing value, then publishes each group to its corresponding
        stream in an efficient batch operation. Unroutable messages are tracked separately.

        Args:
            message_payloads: List of message dicts to route and publish.

        Returns:
            Dict with keys as stream names and values as lists of Redis message IDs,
            plus an 'unroutable' key containing any messages that couldn't be routed.
        """

        # 1. Group messages by their destination stream
        grouped_messages: Dict[str, list] = {
            routing_value: [] for routing_value in self.publishers
        }
        grouped_messages["unroutable"] = []

        for payload in message_payloads:
            routing_value: str = get_nested_value(payload, self.routing_key)

            if routing_value in self.publishers:
                grouped_messages[routing_value].append(payload)
            else:
                grouped_messages["unroutable"].append(payload)
                self.logger.error(
                    f"Message with routing value '{routing_value}' is unroutable."
                )

        # 2. Publish each group of messages to their respective stream
        results = {}

        for routing_value, payloads in grouped_messages.items():
            if not payloads:
                continue

            if routing_value == "unroutable":
                results["unroutable"] = payloads
                continue

            publisher = self.publishers[routing_value]
            result_ids = publisher.publish_many(payloads)
            results[publisher.stream_name] = result_ids

        return results

    @staticmethod
    def generate_router_mapping(
        output_streams: List[str], router_key_values: List[str]
    ):
        """Generates a routing map from parallel lists of values and stream names.

        Creates a dict mapping each router key value to its corresponding output stream.
        Used to bootstrap the routing_map constructor parameter.

        Args:
            output_streams: List of destination Redis stream names (e.g., ['user:to.be.nlp', 'background:to.be.nlp']).
            router_key_values: Corresponding list of routing values (e.g., ['user', 'background']).
                Must be same length as output_streams.

        Returns:
            Dict mapping routing value -> stream name (e.g., {'user': 'user:to.be.nlp', ...}).

        Raises:
            ValueError: If either list is empty or lengths don't match.
        """
        if not output_streams:
            raise ValueError("Missing output_streams")

        if not router_key_values:
            raise ValueError("Missing router_key_values")

        if len(output_streams) != len(router_key_values):
            raise ValueError("Incompatible output_streams router_key_values")

        mapping = {}
        for router_key, stream in zip(router_key_values, output_streams):
            mapping[router_key] = stream

        return mapping
