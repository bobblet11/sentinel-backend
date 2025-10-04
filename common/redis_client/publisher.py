from typing import Any, Dict, Optional
from redis_client.connection import redis_connection
from models.redis_models import Message
import json

class RedisPublisher:    
	"""
	A high-level, reliable wrapper for Redis stream-based FIFO queues.

	This class provides a simple interface to treat a Redis stream like a job
	queue. It handles JSON serialization/deserialization, connection management,
	and basic error handling.

	It is designed to be used with a producer-consumer pattern, where producers
	`push` jobs and consumers `pop` jobs.

	Attributes:
		stream_name (str): The name of the Redis stream used as the queue.
		client: The connected redis-py client instance, managed by the
			RedisConnection singleton.
		max_len (int): maximum number of messages in queue before a message is removed (allows for prioritisation of messages)
	"""
	
	def __init__(self, stream_name: str):
		"""
		Initializes the RedisPublisher instance.

		Args:
		stream_name (str): The name of the Redis stream to use as a queue.

		Raises:
		ValueError: If the stream_name is empty.
		"""
  
		if not isinstance(stream_name, str) or not stream_name:
			raise ValueError("Stream name must be a non-empty string.")

		self.stream_name = stream_name
		self.max_len = 100
		self.client = redis_connection.get_client()
		print(f"Redis publisher initialised for {stream_name}")
  
  
	def publish(self, data: Dict[str, Any]):
		"""
		Serializes a data dictionary to JSON and adds it to the stream.

		Args:
		data: a message object that has been deserialised into a dictionary, that is waiting to be published
  
		Returns:
		str: The unique message ID if successful, otherwise None.
		"""
  
		try:
			payload = {'payload': json.dumps(data)}
			redis_message_id = self.client.xadd(
				self.stream_name,
				payload,
				maxlen=self.max_len,
				approximate=True
			)
			print(f"Published message {data.header.message_id} to {self.stream_name}. [ REDIS_MESSAGE_ID: {redis_message_id} ]")
			return data.header.message_id

		except TypeError as e:
			print(f"Failed to serialize data for '{self.stream_name}': {e}. Data not published.")
			return None

		except Exception as e:
			print(f"Failed to publish message {data.header.message_id} to {self.stream_name}: {e}. Data not published")
			return None
		
