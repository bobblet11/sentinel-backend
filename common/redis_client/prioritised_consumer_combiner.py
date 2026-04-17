from enum import StrEnum
import json
import redis
import math
from typing import Any, Dict, List, Optional
from logging import Logger, getLogger

from common.models.api.dtos.job import JobType
from common.redis_client.connection import redis_connection

DEFAULT_BLOCK_MS = 5_000
MIN_BLOCK_MS = 1_000

class BlockPrioritisationLevel(StrEnum):
    EXPONENTIAL = "exponential"
    LINEAR = "linear"
    UNIFORM_5 = "uniform_5"
    

class PrioritisedRedisConsumerCombiner:
    """
    A higher-level consumer that fetches messages from multiple Redis streams
    in a single, efficient operation.

    It listens to all specified streams simultaneously and returns messages
    from whichever stream has them available first.
    """

    def __init__(self, stream_to_block_map: Optional[Dict[str,int]], group_name: str, consumer_name: str, stream_to_priority_map: Dict[str, int]) -> None:
        """
        Initializes the RedisConsumerCombiner.
        """
        
        if not isinstance(stream_to_priority_map, dict) or not stream_to_priority_map:
            raise ValueError("stream_to_priority_map must be a non-empty dict.")
        
        if not isinstance(consumer_name, str) or not consumer_name:
            raise ValueError("consumer_name must be a non-empty string.")
        
        if not isinstance(group_name, str) or not group_name:
            raise ValueError("group_name must be a non-empty string.")

        if not stream_to_block_map:
            stream_to_block_map = {stream_name: DEFAULT_BLOCK_MS for stream_name in stream_to_priority_map.keys()}
        else:
            stream_to_block_map = {
                stream_name: (block if block >= MIN_BLOCK_MS else DEFAULT_BLOCK_MS)
                for stream_name, block in stream_to_block_map.items()
            }
        
        if set(stream_to_priority_map.keys()) != set(stream_to_block_map.keys()):
            raise ValueError("stream_to_priority_map and stream_to_block_map must match.")
        

        self.logger: Logger = getLogger(f"{consumer_name}.redis_consumer_combiner")
        self.stream_to_priority_map:Dict[str,int] = stream_to_priority_map
        self.stream_to_block_map:Dict[str,int] = stream_to_block_map
        self.group_name:str = group_name
        self.consumer_name:str = consumer_name
        self.client:redis.Redis = redis_connection.get_client()
        self._create_groups()
        self.logger.info(f"PrioritisedConsumerCombiner ready: streams={list(self.stream_to_priority_map.keys())}, group='{self.group_name}'")

    def _create_groups(self) -> None:
        """
        Idempotently creates the consumer group on all streams.
        """
        streams:List[str] = self.stream_to_priority_map.keys()
        for stream in streams:
            try:
                # Use '0' to read the entire history if the group is new,
                # or '$' to only get new messages. '0' is often safer for dev.
                self.client.xgroup_create(
                    stream, self.group_name, id="0", mkstream=True
                )
                self.logger.info(f"Created group '{self.group_name}' on stream '{stream}'.")

            except redis.exceptions.ResponseError as e:
                if "BUSYGROUP" not in str(e):
                    raise e
                self.logger.debug(f"Group '{self.group_name}' already exists on stream '{stream}'.")

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

    def consume_one(self) -> Optional[Dict[str, Any]]:
        """
        Waits for and consumes ONE message from the configured streams in prioritised order.
        
        Args:
            block: Time in milliseconds to wait before timing out.
            
        Returns:
            A single decoded message dictionary, or None if the operation timed out.
        """
        try:
            for stream_name in sorted(self.stream_to_priority_map, key=self.stream_to_priority_map.get):
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

    def consume_many(
        self, num_to_consume: int = 1
    ) -> Optional[List[Dict[str, Any]]]:
        
        """
        Waits for and consumes up to N messages from the configured streams in prioritised order.

        Args:
            num_to_consume: The maximum number of messages to consume from a stream.
            block: Time in milliseconds to wait before timing out.

        Returns:
            A list of decoded message dictionaries, or an empty list on timeout.
        """
    
        try:
            for stream_name in sorted(self.stream_to_priority_map, key=self.stream_to_priority_map.get):
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
                
                messages = [self._decode_one_message(stream_name, redis_message_id, fields) for redis_message_id, fields in messages]
                return messages
            return None
        except Exception as e:
            self.logger.error(f"Could not consume a any messages: {e}")
            raise e

    def consume_pending(self) -> Optional[List[Dict[str, Any]]]:
        """
        Consumes messages that are pending for this specific consumer.
        This should be called on startup to recover from a previous crash.

        Redis cluster mode does not allow multi-stream XREADGROUP calls when the
        stream keys live in different hash slots, so we read pending entries one
        stream at a time in priority order.
        """

        try:
            all_messages: List[Dict[str, Any]] = []

            for stream_name in sorted(self.stream_to_priority_map, key=self.stream_to_priority_map.get):
                response = self.client.xreadgroup(
                    self.group_name,
                    self.consumer_name,
                    streams={stream_name: "0-0"},
                )

                if not response:
                    continue

                _, messages = response[0]
                for redis_message_id, fields in messages:
                    message_dict:Dict[str, Any] = self._decode_one_message(
                        stream_name, redis_message_id, fields
                    )
                    all_messages.append(message_dict)

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
            self.client.hincrby(f"stream:{stream_name}:group:{self.group_name}:acks", self.consumer_name, 1)
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
            ack_result = self.client.xack(stream_name, self.group_name, redis_message_id)
            if ack_result == 0:
                raise Exception("Failed to ack")
            self.client.hincrby(f"stream:{stream_name}:group:{self.group_name}:acks", self.consumer_name, 1)
            del_result = self.client.xdel(stream_name, redis_message_id)
            if del_result == 0:
                raise Exception("Failed to del")
            
            self.logger.debug(f"Successfully acknowledged and cleaned up {redis_message_id}")
        except Exception as e:
            self.logger.error(
                f"Failed to acknowledging message {redis_message_id} on stream {stream_name}: {e}"
            )
            raise e
        
    @staticmethod
    def generate_stream_to_priority_mapping(input_streams:List[str]):
        """Assume that the order of the list of input streams indicated priority order. First is highest priority."""
        if not input_streams:
            raise ValueError("Missing input_streams")
        
        mapping = {}
        for i in range(len(input_streams)):
            mapping[input_streams[i]] = i+1
        return mapping
    
    @staticmethod
    def generate_stream_to_block_mapping(input_streams:List[str], level: BlockPrioritisationLevel = BlockPrioritisationLevel.LINEAR, minimum_block_ms:int = MIN_BLOCK_MS):
        """Assume that the order of the list of input streams indicated priority order. First is highest priority."""
        if not input_streams:
            raise ValueError("Missing input_streams")
        
        mapping = {}
        
        LINEAR_GRADIENT = 2000 
        EXPONENTIAL_BASE = 2  
        input_streams_length = len(input_streams)
        for priority_index, stream_name in enumerate(input_streams):
            inverse_priority_index = (input_streams_length - 1) - priority_index
            
            if level is BlockPrioritisationLevel.LINEAR:
                mapping[stream_name] = minimum_block_ms + (LINEAR_GRADIENT * inverse_priority_index)
            
            elif level is BlockPrioritisationLevel.EXPONENTIAL:
                mapping[stream_name] = minimum_block_ms * (EXPONENTIAL_BASE ** inverse_priority_index)

            elif level is BlockPrioritisationLevel.UNIFORM_5:
                mapping[stream_name] = 5_000
            
            else:
                raise ValueError(f"Invalid prioritisation level provided: {level}")
        return mapping
