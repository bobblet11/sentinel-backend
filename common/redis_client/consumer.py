from logging import Logger, getLogger
import redis
import json
from typing import Any, Dict, List, Optional
from common.redis_client.connection import redis_connection


class RedisConsumer:
    """
    A high-level, reliable wrapper for Redis stream-based FIFO queues.
    """

    def __init__(self, stream_name: str, group_name: str, consumer_name: str) -> None:
        """
        stream_name (str): The name of the Redis stream to listen to.
        group_name (str): The name of the Redis group to listen to.
        consumer_name (str): The name redis is told when a message is consumed.
        """
        
        if not isinstance(stream_name, str) or not stream_name:
            raise ValueError("stream_name must be a non-empty str.")
        
        if not isinstance(consumer_name, str) or not consumer_name:
            raise ValueError("consumer_name must be a non-empty string.")
        
        if not isinstance(group_name, str) or not group_name:
            raise ValueError("group_name must be a non-empty string.")

        self.logger: Logger = getLogger(f"{consumer_name}.redis_consumer")
        self.logger.info("--- Initializing RedisConsumer ---")
        self.stream_name:List[str] = stream_name
        self.group_name:str = group_name
        self.consumer_name:str = consumer_name
        self.client:redis.Redis = redis_connection.get_client()
        
        self.logger.info(f"Stream Name: '{self.stream_name}', Group Name: '{self.group_name}', Consumer Name: '{self.consumer_name}'")
        self._create_group()
        self.logger.info("--- Initialized RedisConsumer ---")

    def _create_group(self) -> None:
        """
        Indempotently creates the consumer group on the stream if it doesn't already exist.
        """
        try:
            # XGROUP CREATE <stream> <group> $ MKSTREAM
            # '$' means start reading from the end of the stream (only new messages).
            # MKSTREAM will create the stream if it doesn't exist.
            
            
            
            # 0: This special ID signifies that the consumer group should start reading from the very beginning of the stream, consuming every message that has ever been published to it.[1][2]
            # $: This special ID tells the consumer group to only start consuming new messages that arrive after the group was created. It will not receive any of the messages that are already in the stream.[1]
            # A specific message ID: You can provide any valid message ID. The consumer group will then start reading messages that come after that specific ID.
            
            self.client.xgroup_create(
                self.stream_name, self.group_name, id="0", mkstream=True
            )
            
            self.logger.info(f"Created group '{self.group_name}' on stream '{self.stream_name}'.")
                
        except redis.exceptions.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise e
            self.logger.error(f"Group '{self.group_name}' already exists on stream '{self.stream_name}'.")

    def _decode_one_message(self, stream_name:str, redis_message_id:str, fields:Dict[str, Any]) -> Dict[str, Any]:
        """
        Decodes a single raw message from Redis, handling byte conversion and JSON parsing.
        """
        decoded_fields: Dict[str, Any] = fields
        message_data:Dict[str, Any] = {}
        
        if "payload" in decoded_fields:
            message_data = json.loads(decoded_fields["payload"])
        else:
            self.logger.warning(f"Message {redis_message_id} is missing 'payload' field.")
            message_data = decoded_fields

        return {
            "stream": stream_name,
            "redis_message_id": redis_message_id, 
            "data": message_data,
        }

    def consume_one(self, block: int = 0) -> Optional[Dict[str, Any]]:
        """
        Waits for and consumes ONE new raw message from the stream.

        Returns:
                A dictionary like {'redis_message_id': '...', 'payload': {...}},
                or None if the operation timed out.
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
            
            stream_name:str
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
        """
        Waits for and consumes N new raw message from the stream.

        Returns:
                A dictionary like {'redis_message_id': '...', 'payload': {...}},
                or None if the operation timed out.
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
                        
                        message_dict:Dict[str, Any] = self._decode_one_message(
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
        """
        Consumes messages that are pending for this specific consumer.
        This should be called on startup to recover from a previous crash.
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
                        message_dict:Dict[str, Any] = self._decode_one_message(
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
        """
        Acknowledges that a message from a specific stream has been processed.
        """
        
        try:
            result = self.client.xack(
                self.stream_name, self.group_name, redis_message_id
            )
            if result == 0:
                raise Exception("Failed to ack")
            self.logger.debug(f"Successfully acknowledged {redis_message_id}")
            
        except Exception as e:
            self.logger.error(
                f"Failed to acknowledging message {redis_message_id} on stream {self.stream_name}: {e}"
            )
            raise e
    
    def acknowledge_and_delete(self, stream_name: str, redis_message_id: str) -> None:
        """
        Acknowledges that a message from a specific stream has been processed and deletes it from last stream
        """
        
        try:
            ack_result = self.client.xack(stream_name, self.group_name, redis_message_id)
            if ack_result == 0:
                raise Exception("Failed to ack")
            
            del_result = self.client.xdel(stream_name, redis_message_id)
            if del_result == 0:
                raise Exception("Failed to del")
            
            self.logger.debug(f"Successfully acknowledged and cleaned up {redis_message_id}")
        except Exception as e:
            self.logger.error(
                f"Failed to acknowledging message {redis_message_id} on stream {stream_name}: {e}"
            )
            raise e
