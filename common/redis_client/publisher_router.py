import hashlib
from typing import Any, Dict, List, Optional
from common.redis_client.publisher import RedisPublisher
from logging import Logger, getLogger

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

    def __init__(self, routing_map: Dict[str, str], routing_key: List[str]):
        """
        Initializes the RedisPublisherRouter with a map of message types to stream names.

        Args:
            routing_map (Dict[str, str]): A dictionary where keys are the expected
                                         message types (e.g., "user", "background")
                                         and values are the target Redis stream names
                                         (e.g., "user-nlp-jobs", "background-nlp-jobs").

            routing_key (List[str]): The key within an incoming message dictionary that
                               contains the message type string.
        """

        if not isinstance(routing_map, dict) or not routing_map:
            raise ValueError("routing_map must be a non-empty dictionary.")
        
        if not isinstance(routing_key, list) or not routing_key:
            raise ValueError("routing_key must be a non-empty list of strings.")

        unique_handle: str = hashlib.md5(str(routing_map).encode("utf-8")).hexdigest()[:5]
        self.logger: Logger = getLogger(f"{unique_handle}.redis_publisher_router")
        self.logger.info("--- Initializing RedisPublisherRouter ---")
        
        self.routing_map:Dict[str,str] = routing_map
        self.routing_key:List[str] = routing_key
        self.publishers: Dict[str, RedisPublisher] = {}

        for message_type, stream_name in self.routing_map.items():
            self.logger.info(
                f"Mapping messages of type '{message_type}' -> stream '{stream_name}'"
            )
            self.publishers[message_type] = RedisPublisher(stream_name)
            
        self.logger.info(f"--- Initialized RedisPublisherRouter ---")

    def publish_one(self, message_payload: Dict[str, Any]) -> str:
        """
        Inspects a message, determines its type using the routing_key, and
        forwards it to the correct Redis stream publisher.

        Args:
            message: The message dictionary to be published. It must contain
                     the routing_key.

        Returns:
            The unique Redis message ID if publishing was successful, otherwise None.
        """
    
        # 1. Determine the route
        routing_value:str = self._get_nested_value(message_payload, self.routing_key)
        if not routing_value:
            raise Exception(f"Routing key '{self.routing_key}' not found in message. Message not published.")

        # 2. Find the correct publisher for that route
        publisher:RedisPublisher = self.publishers.get(routing_value, None)
        if publisher is None:
            raise Exception(f"No publisher configured for routing value '{routing_value}'. Message not published.")

        # 3. Use the dedicated publisher to send the message
        self.logger.debug(f"Routing message of routing value '{routing_value}' to stream '{publisher.stream_name}'.")
        # can release exception if fails
        return publisher.publish_one(message_payload)

    def _get_nested_value(self, payload:Dict[str,Any], keys: List[str]) -> Any:
        """
        Sets a value deep inside the data dictionary.
        Creates intermediate dictionaries if they don't exist.
        Usage: msg.set_nested(html_content, "data", "data", "html")
        """
        if not keys or not payload:
            raise Exception("Missing arguments")
        
        current_level = payload
        
        for key in keys[:-1]:
            if key not in current_level or not isinstance(current_level[key], dict):
                raise Exception("Key does not exist in payload!")
            
            current_level:Dict[str, Any] = current_level[key]
        
        value:Any = current_level[keys[-1]]
        return value
    
    def publish_many(self, message_payloads: List[Dict[str, Any]]) -> Dict[str, int]:
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

        unroutable_count:int = 0
        for payload in message_payloads:
            message_type:str = payload.get(self.routing_key, None)
            
            if message_type not in grouped_messages:
                unroutable_count += 1
                continue
            
            grouped_messages[message_type].append(payload)

        if unroutable_count > 0:
            self.logger.warning(
                f"{unroutable_count} messages have are not mapped to any publisher in map. These {unroutable_count} messages were not published."
            )


        # 2. Publish each group of messages to their respective stream
        results:Dict[str, int] = {}
        
        for message_type, payloads in grouped_messages.items():
            if len(payloads) == 0:
                continue

            publisher:RedisPublisher = self.publishers[message_type]
            result_ids:List[str] = publisher.publish_many(payloads)
            results[publisher.stream_name] = len(result_ids)

        return results
