from typing import Any, Dict, Optional
from .connection import redis_connection
from common.models.redis_models import Message
import json	

class RedisConsumer:    
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
		group_name: name of group to listen to (like a bookmark)
		consumer_name: name given to redis when a message is consumed from stream.
	"""
	
	def __init__(self, stream_name: str, group_name:str, consumer_name:str):
		"""
		Initializes the RedisConsumer instance.

		Args:
			stream_name (str): The name of the Redis stream to listen to.
			group_name (str): The name of the Redis group to listen to.
			consumer_name (str): The name redis is told when a message is consumed.
		Raises:
			ValueError: If the stream_name is empty.
			ValueError: If the group_name is empty.
   			ValueError: If the consumer_name is empty.
		"""
  
		if not isinstance(stream_name, str) or not stream_name:
			raise ValueError("Stream name must be a non-empty string.")

		if not isinstance(group_name, str) or not group_name:
			raise ValueError("Group name must be a non-empty string.")


		if not isinstance(consumer_name, str) or not consumer_name:
			raise ValueError("Consumer name must be a non-empty string.")



		self.stream_name = stream_name
		self.group_name = group_name
		self.consumer_name = consumer_name
  
		self.max_len = 100
		self.client = redis_connection.get_client()
  
		print(f"Redis consumer initialised for {stream_name}, group {group_name}, consumer name {consumer_name}")

	def _create_group(self):
		"""
		Creates the consumer group on the stream if it doesn't already exist.
		This is an idempotent operation.
		"""
		try:
			# XGROUP CREATE <stream> <group> $ MKSTREAM
			# '$' means start reading from the end of the stream (only new messages).
			# MKSTREAM will create the stream if it doesn't exist.
			self.client.xgroup_create(self.stream_name, self.group_name, id='$', mkstream=True)
			print(f"Created consumer group '{self.group_name}' on stream '{self.stream_name}'.")
   
		except Exception as e:
			# This is expected if the group already exists.
			if "BUSYGROUP" in str(e):
				print(f"Consumer group '{self.group_name}' already exists.")
			else:
				print(f"Error creating consumer group: {e}")
				raise

	def consume(self, block: int = 0) -> Optional[Dict[str, Any]]:
		"""
		Waits for and consumes ONE new raw message from the stream.
		This method does NOT perform any Pydantic validation.

		Returns:
		A dictionary like {'redis_message_id': '...', 'payload': {...}},
		or None if the operation timed out.
		"""
		try:
			response = self.client.xreadgroup(
				self.group_name,
				self.consumer_name,
				{self.stream_name: '>'},
				count=1,
				block=block
			)
		
			if not response:
				return None
			
			redis_message_id = response[0][1][0][0]
			# Return the RAW payload. Let the caller handle validation.
			payload_json = response[0][1][0][1]['payload']
			payload_dict = json.loads(payload_json)
			
			return {'redis_message_id': redis_message_id, 'payload': payload_dict}

		except json.JSONDecodeError as e:
			print(f"CORRUPTED MESSAGE: Failed to decode JSON from stream '{self.stream_name}'. Raw data: '{payload_json}'. Error: {e}")
			raise 
		except Exception as e:
			print(f"Error consuming from stream '{self.stream_name}': {e}")
			raise # Re-raise unexpected errors

	def acknowledge(self, message_id: str):
		"""
		Acknowledges that a message has been successfully processed, removing it
		from the Pending Entries List (PEL) for this consumer group.

		This allows the group to shift to the next message so that any other listeners can get the next message.
  
		Args:
			message_id (str): The ID of the message to acknowledge.
		"""
		try:
			# XACK <stream> <group> <id>
			self.client.xack(self.stream_name, self.group_name, message_id)
			print(f"Acknowledged message {message_id} in group '{self.group_name}'.")
		except Exception as e:
			print(f"Error acknowledging message {message_id}: {e}")