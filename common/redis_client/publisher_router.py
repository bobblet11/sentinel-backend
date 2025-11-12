from typing import Any, Dict, List, Optional

from common.redis_client.publisher import RedisPublisher


class RedisPublisherRouter:
    """
    A higher-level publisher that acts as a router, forwarding messages
    to different Redis streams based on a specific key within the message.

    This class creates and manages multiple RedisPublisher instances, one for
    each destination stream defined in the routing map.

    Example:
        splitter = RedisPublisherRouter({'user':'123', 'background' : '456'}, 'type')
        splitter.publish_one({'type':'user'})           //publishes to 123
        splitter.publish_one({'type':'background'})     //publishes to 456
        splitter.publish_one({'type':'unknown'})        //fails, unknown mapping
    """

    def __init__(self, routing_map: Dict[str, str], routing_key: str):
        """
        Initializes the RedisPublisherRouter with a map of message types to stream names.

        Args:
            routing_map (Dict[str, str]): A dictionary where keys are the expected
                                         message types (e.g., "user", "background")
                                         and values are the target Redis stream names
                                         (e.g., "user-nlp-jobs", "background-nlp-jobs").

            routing_key (str): The key within an incoming message dictionary that
                               contains the message type string.
        """

        if not isinstance(routing_map, dict) or not routing_map:
            raise ValueError("routing_map must be a non-empty dictionary.")
        if not isinstance(routing_key, str) or not routing_key:
            raise ValueError("routing_key must be a non-empty string.")

        self.routing_map = routing_map
        self.routing_key = routing_key
        self.publishers: Dict[str, RedisPublisher] = {}

        print("--- Initializing RedisPublisherSplit ---")

        # For each route, create and store a dedicated RedisPublisher instance
        for message_type, stream_name in self.routing_map.items():
            print(
                f"  - Mapping message type '{message_type}' -> stream '{stream_name}'"
            )
            self.publishers[message_type] = RedisPublisher(stream_name)
        print("--------------------------------------")

    def publish_one(self, message: Dict[str, Any]) -> Optional[str]:
        """
        Inspects a message, determines its type using the routing_key, and
        forwards it to the correct Redis stream publisher.

        Args:
            message: The message dictionary to be published. It must contain
                     the routing_key.

        Returns:
            The unique Redis message ID if publishing was successful, otherwise None.
        """
        try:
            # 1. Determine the route
            message_type = message.get(self.routing_key)
            if message_type is None:
                print(
                    f"ERROR: Routing key '{self.routing_key}' not found in message. Message not published."
                )
                return None

            print(f"MessageType: {message_type}")

            # 2. Find the correct publisher for that route
            publisher = self.publishers.get(message_type)
            if publisher is None:
                print(
                    f"ERROR: No publisher configured for message type '{message_type}'. Message not published."
                )
                return None

            print(f"Publisher: {publisher}")

            # 3. Use the dedicated publisher to send the message
            print(
                f"Routing message of type '{message_type}' to stream '{publisher.stream_name}'..."
            )
            return publisher.publish_one(message)

        except Exception as e:
            print(
                f"An unexpected error occurred in RedisPublisherSplit.publish_one: {e}"
            )
            return None

    def publish_many(self, messages: List[Dict[str, Any]]) -> Dict[str, int]:
        """
        Groups a list of messages by their type and publishes each group
        to its corresponding stream in an efficient batch.

        Args:
            messages: A list of message dictionaries to be published.

        Returns:
            A dictionary summarizing the count of messages published to each stream.
        """
        # 1. Group messages by their destination stream
        grouped_messages: Dict[str, List[Dict[str, Any]]] = {
            message_type: [] for message_type in self.publishers.keys()
        }

        unroutable_count = 0
        for message in messages:
            message_type = message.get(self.routing_key)
            if message_type in grouped_messages:
                grouped_messages[message_type].append(message)
            else:
                unroutable_count += 1

        if unroutable_count > 0:
            print(
                f"Warning: {unroutable_count} messages had an unknown or missing route and were ignored."
            )

        # 2. Publish each group using the appropriate publisher's batch method
        summary = {}
        for message_type, message_list in grouped_messages.items():
            if not message_list:
                continue

            publisher = self.publishers[message_type]
            print(
                f"Batch publishing {len(message_list)} messages of type '{message_type}'..."
            )
            result_ids = publisher.publish_many(message_list)
            if result_ids:
                summary[publisher.stream_name] = len(result_ids)

        return summary
