import os
import socket
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

    def __init__(self, streams: List[str], group_name: str):
        """
        Initializes the RedisConsumerCombiner.

        Args:
            streams (List[str]): A list of stream names to listen to.
            group_name (str): The single group name this consumer will use across all streams.
        """
        if not isinstance(streams, list) or not streams:
            raise ValueError("streams must be a non-empty list.")
        if not isinstance(group_name, str) or not group_name:
            raise ValueError("group_name must be a non-empty string.")

        self.streams = streams
        self.group_name = group_name
        
        # Generate a single, unique consumer name for this process.
        # This one worker will be responsible for messages from all streams it pulls.
        self.consumer_name = f"{socket.gethostname()}-{os.getpid()}"
        
        # We only need one client to talk to Redis.
        self.client = redis_connection.get_client()

        print("--- Initializing RedisConsumerCombiner ---")
        print(f"  - Group: '{self.group_name}', Consumer: '{self.consumer_name}'")
        self._create_groups()
        print("--------------------------------------")

    def _create_groups(self):
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
                print(f"  - Created group '{self.group_name}' on stream '{stream}'.")
            except redis.exceptions.ResponseError as e:
                if "BUSYGROUP" in str(e):
                    print(f"  - Group '{self.group_name}' already exists on stream '{stream}'.")
                else:
                    raise

    def consume_one(self, block: int = 0) -> Optional[Dict[str, Any]]:
        """
        Waits for and consumes ONE message from ANY of the configured streams.

        It returns the first message that becomes available. If multiple streams
        had data when called, it returns the first message from the first stream
        in the Redis response.

        Returns:
            A single decoded message dictionary, or None if the operation timed out.
        """
        try:
            streams_dict = {stream: ">" for stream in self.streams}
            
            response = self.client.xreadgroup(
                self.group_name,
                self.consumer_name,
                streams=streams_dict,
                count=1,
                block=block,
            )

            if not response:
                return None

            # The response is [[stream_name, [message_tuple]]]. We just need the first one.
            stream_name, messages = response[0]
            message_id, fields = messages[0]

            return {
                'stream': stream_name,
                'message_id': message_id,
                'data': fields
            }
        
        except Exception as e:
            print(f"An error occurred in RedisConsumerCombiner.consume_one: {e}")
            return None
    def consume_many(self, num_to_consume: int = 1, block: int = 0) -> List[Dict[str, Any]]:
        """
        Waits for and consumes up to N messages from ANY of the configured streams.

        Args:
            num_to_consume: The maximum number of messages to consume from each stream.
            block: Time in milliseconds to wait before timing out.

        Returns:
            A list of decoded message dictionaries, or an empty list on timeout.
        """
        all_messages = []
        try:
            streams_dict = {stream: ">" for stream in self.streams}
            
            response = self.client.xreadgroup(
                self.group_name,
                self.consumer_name,
                streams=streams_dict,
                count=num_to_consume,
                block=block,
            )

            if not response:
                return all_messages

            # Loop through the response which may contain messages from multiple streams
            for stream_name, messages in response:
                for message_id, fields in messages:
                    message_dict = {
                        'stream': stream_name,
                        'message_id': message_id,
                        'data': fields
                    }
                    all_messages.append(message_dict)

            return all_messages
        except Exception as e:
            print(f"An error occurred in RedisConsumerCombiner.consume_many: {e}")
            return all_messages

    def acknowledge(self, stream_name: str, message_id: str):
        """
        Acknowledges that a message from a specific stream has been processed.
        You must know which stream the message came from.
        """
        # This method can be simple, just calling the client directly.
        try:
            self.client.xack(stream_name, self.group_name, message_id)
        except Exception as e:
            print(f"Error acknowledging message {message_id} on stream {stream_name}: {e}")
            raise
