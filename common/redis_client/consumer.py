import json
from typing import Any, Dict, List, Optional

from common.redis_client.connection import redis_connection


class RedisConsumer:
    """
    A high-level, reliable wrapper for Redis stream-based FIFO queues.

    Attributes:
            stream_name (str): The name of the Redis stream used as the queue.
            client: The connected redis-py client instance, managed by the RedisConnection singleton.
            max_len (int): maximum number of messages in queue before a message is removed (allows for prioritisation of messages)
            group_name: name of group to listen to (like a bookmark)
            consumer_name: name given to redis when a message is consumed from stream.
    """

    def __init__(self, stream_name: str, group_name: str, consumer_name: str):
        """
        stream_name (str): The name of the Redis stream to listen to.
        group_name (str): The name of the Redis group to listen to.
        consumer_name (str): The name redis is told when a message is consumed.
        """

        if not isinstance(stream_name, str) or not stream_name:
            raise ValueError("Stream name must be a non-empty string.")

        if not isinstance(group_name, str) or not group_name:
            raise ValueError("Group name must be a non-empty string.")

        self.stream_name = stream_name
        self.group_name = group_name
        self.consumer_name = consumer_name
        self.max_len = 100
        self.client = redis_connection.get_client()

        print(
            f"Redis consumer initialised and listening to {stream_name}, group {group_name} under the name {consumer_name}"
        )

    def _create_group(self):
        """
        Indempotently creates the consumer group on the stream if it doesn't already exist.
        """
        try:
            # XGROUP CREATE <stream> <group> $ MKSTREAM
            # '$' means start reading from the end of the stream (only new messages).
            # MKSTREAM will create the stream if it doesn't exist.
            self.client.xgroup_create(
                self.stream_name, self.group_name, id="$", mkstream=True
            )
            print(
                f"Created consumer group '{self.group_name}' on stream '{self.stream_name}'."
            )

        except Exception as e:
            if "BUSYGROUP" in str(e):
                print(f"Consumer group '{self.group_name}' already exists.")
            else:
                print(f"Error creating consumer group: {e}")
                raise

    def __decode_one_message(self, stream_name, redis_message_id, fields):
        decoded_fields = fields

        if "payload" in decoded_fields:
            message_data = json.loads(decoded_fields["payload"])
        else:
            print(f"Warning: Message {redis_message_id} is missing 'payload' field.")
            message_data = decoded_fields

        message_dict = {
            "stream": stream_name,
            "redis_message_id": redis_message_id,
            "data": message_data,
        }

        return message_dict

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
                {self.stream_name: ">"},
                count=1,
                block=block,
            )

            if not response:
                None

            stream_name, messages = response[0]
            redis_message_id, fields = messages[0]

            return self.__decode_one_message(stream_name, redis_message_id, fields)

        except json.JSONDecodeError as e:
            print(
                f"CORRUPTED MESSAGE: Failed to decode JSON from stream '{self.stream_name}'. Error: {e}"
            )
            raise

        except Exception as e:
            print(f"Error consuming from stream '{self.stream_name}': {e}")
            raise

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
                {self.stream_name: ">"},
                count=num_to_consume,
                block=block,
            )

            if not response:
                return all_messages

            for stream_name, messages in response:
                for redis_message_id, fields in messages:
                    try:
                        message_dict = self.__decode_one_message(
                            stream_name, redis_message_id, fields
                        )
                        all_messages.append(message_dict)
                    except json.JSONDecodeError as e:
                        msg_id_str = redis_message_id
                        print(
                            f"CORRUPTED MESSAGE: Skipping message {msg_id_str} due to JSON decode error: {e}"
                        )
                        continue

            return all_messages

        except Exception as e:
            print(f"Error consuming from stream '{self.stream_name}': {e}")
            raise

    def acknowledge(self, redis_message_id: str):
        """
        Acknowledges that a message from a specific stream has been processed.
        """
        try:
            result = self.client.xack(
                self.stream_name, self.group_name, redis_message_id
            )
            if result == 0:
                print(
                    f"Warning: Acknowledgment for message {redis_message_id} on stream {self.stream_name} failed."
                )
        except Exception as e:
            print(
                f"Error acknowledging message {redis_message_id} on stream {self.stream_name}: {e}"
            )
            raise
