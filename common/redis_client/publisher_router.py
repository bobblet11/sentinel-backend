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
        self.routing_map:Dict[str,str] = routing_map
        self.routing_key:List[str] = routing_key
        self.publishers: Dict[str, RedisPublisher] = {}

        for message_type, stream_name in self.routing_map.items():
            self.publishers[message_type] = RedisPublisher(stream_name)

        self.logger.info(f"PublisherRouter ready: {routing_map}")


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
        grouped_messages: Dict[str, list] = {routing_value: [] for routing_value in self.publishers}
        grouped_messages["unroutable"] = []

        for payload in message_payloads:
            routing_value:str = get_nested_value(payload, self.routing_key)
            
            if routing_value in self.publishers:
                grouped_messages[routing_value].append(payload)
            else:
                grouped_messages["unroutable"].append(payload)
                self.logger.error(f"Message with routing value '{routing_value}' is unroutable.")

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
    def generate_router_mapping(output_streams:List[str], router_key_values:List[str]):
        """Assume that the order of the list of input streams indicated priority order. First is highest priority."""
        if not output_streams:
            raise ValueError("Missing output_streams")
        
        if not router_key_values:
            raise ValueError("Missing router_key_values")
        
        if len(output_streams) != len(router_key_values):
            raise ValueError("Incompatible output_streams router_key_values")
        
        mapping = {}
        for router_key, stream  in zip(router_key_values, output_streams):
            mapping[router_key] = stream
            
        return mapping
    