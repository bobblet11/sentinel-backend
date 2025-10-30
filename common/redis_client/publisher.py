import json
from typing import Any, Dict, List, Optional

from common.redis_client.connection import redis_connection


class RedisPublisher:
    """
    A high-level, reliable wrapper for Redis stream-based FIFO queues.

    Attributes:
            stream_name (str): The name of the Redis stream used as the queue.
            client: The connected redis-py client instance, managed by the
                    RedisConnection singleton.
            max_len (int): maximum number of messages in queue before a message is removed (allows for prioritisation of messages)
    """

    def __init__(self, stream_name: str):
        """
        Args:
        stream_name (str): The name of the Redis stream to publish to.
        """

        if not isinstance(stream_name, str) or not stream_name:
            raise ValueError("Stream name must be a non-empty string.")

        self.stream_name = stream_name
        self.max_len = 100000
        self.client = redis_connection.get_client()

        print(f"Redis publisher initialised and publishing to {stream_name}")

    def publish_one(self, message: Dict[str, Any]):
        """
        Serializes a dictionary to JSON and adds it to the stream.

        Args:
                message: a message object that has been deserialised into a dictionary, that is waiting to be published

        Returns:
                str: The unique message ID if successful, otherwise None.
        """

        try:
            if not message or message == {}:
                print("No message to publish")
                raise Exception("No message to publish")

            payload = {"payload": json.dumps(message)}
            redis_message_id = self.client.xadd(
                self.stream_name, payload, maxlen=self.max_len, approximate=True
            )
            print(
                f"Published message {message.header.message_id} to {self.stream_name}. [ REDIS_MESSAGE_ID: {redis_message_id} ]"
            )
            return redis_message_id

        except TypeError as e:
            print(
                f"Failed to serialize data for '{self.stream_name}': {e}. Data not published."
            )
            return None

        except Exception as e:
            print(
                f"Failed to publish message {message.header.message_id} to {self.stream_name}: {e}. Data not published"
            )
            return None

    def publish_many(self, messages: List[Dict[str, Any]]) -> Optional[List[str]]:
        """
        Serializes messages dictionaries to JSON and adds all to the stream.

        Args:
                messages: A list of JSON-serializable dictionaries, where each
                        dictionary represents a message to be published.
        Returns:
                A list of the unique Redis message IDs for the published messages
                if successful, otherwise None.
        """

        try:
            if not messages or len(messages) == 0:
                print("No messages to publish")
                raise Exception("No messages to publish")

            pipe = self.client.pipeline()

            for message_data in messages:
                payload = {"payload": json.dumps(message_data)}
                pipe.xadd(
                    self.stream_name, payload, maxlen=self.max_len, approximate=True
                )

            message_ids = pipe.execute()

            print(f"Published {len(message_ids)} messages to {self.stream_name}.")
            return message_ids

        except TypeError as e:
            # This specific error is for when json.dumps fails.
            print(
                f"Serialization failed for a message in the batch for stream "
                f"'{self.stream_name}'. No messages were published. Error: {e}"
            )
            return None

        except Exception as e:
            print(
                f"An unexpected error occurred during batch publish to stream "
                f"'{self.stream_name}'. No messages were published. Error: {e}"
            )
            return None
