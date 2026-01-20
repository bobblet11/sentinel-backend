
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from logging import Logger, getLogger
import time
from typing import Any, Dict, List, Optional

from pydantic import ValidationError
from sqlalchemy import Tuple

from common.models.api.redis_models import Message, StreamMessage
from common.redis_client.consumer import RedisConsumer
from common.redis_client.consumer_combiner import RedisConsumerCombiner
from common.redis_client.publisher import RedisPublisher
from common.redis_client.publisher_router import RedisPublisherRouter

PRIORITY_MAP = {
    "user": 1,
    "admin": 1,  
    "background": 2,
    "logging": 3,
}
LOWEST_PRIORITY: float = float("inf")

class ProcessingError(Exception):
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)
        
class RoutingError(Exception):
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)        


@dataclass()
class ServiceConfig():
        service_name:str
        input_streams:List[str]
        group_name:str
        consumer_name:str
        failure_output_stream: str | None # if none, then failed batches will just not be published and will be pending for next cycle
        routing_map: Dict[str,str]
        routing_key:List[str] = ["header","type"]
        is_concurrent: bool = False
        max_workers:int = 1
        batch_size:int = 10

        

class ServiceTemplate(ABC):
	"""Concurrently scrapes, parses, and publishes messages"""

	def __init__(self, config: ServiceConfig ) -> None:
		self.logger: Logger = getLogger(config.service_name)
		self.input_streams = config.input_streams
		self.max_workers = config.max_workers
		self.batch_size = config.batch_size
		self.keep_running: bool = True
		self.is_concurrent = config.is_concurrent
		self.message_consumer = RedisConsumerCombiner(config.input_streams, config.group_name, config.consumer_name)
		self.success_publish_router = RedisPublisherRouter(
			routing_key=config.routing_key, routing_map=config.routing_map
		)
		self.fail_publisher = RedisPublisher(config.failure_output_stream)

	def shutdown(self, *args) -> None:
		"""Signal handler to initiate a graceful shutdown."""
		self.logger.info("\nShutdown signal received. Finishing current batch...")
		self.keep_running = False

	def _handle_failure(self, message: StreamMessage | Dict[str, Any], error: Exception):
		"""Logs the error and publishes the message to the failure stream."""
		is_stream_message:bool = isinstance(message, StreamMessage)
  
		redis_id = message.redis_id if is_stream_message else message.get("redis_message_id", "N/A")
		self.logger.error(f"Failed to process message {redis_id}: {error}")
		
		payload = message.data if is_stream_message else message.get("data", {})
  		# Acknowledge the original message before publishing to failure queue
		self.fail_publisher.publish_one(payload)	
		self.message_consumer.acknowledge(redis_id)
		self.logger.info(f"Message {redis_id} acknowledged and moved to failure stream.")
  
	def _handle_failure_batch(self, messages: List[StreamMessage | Dict[str, Any]], error: Exception):
		"""Logs the error and publishes the message to the failure stream."""
		if not messages:
			self.logger.error("No messages to handle failure")
			return

		is_stream_message:bool = isinstance(messages[0], StreamMessage)

		payloads = [msg.data for msg in messages] if is_stream_message else  [msg.get("data", {}) for msg in messages]
		redis_ids = [msg.redis_id for msg in messages] if is_stream_message else  [msg.get("redis_message_id", "N/A") for msg in messages]
		self.logger.error(f"Failed to process batch of {len(payloads)} messages: {error}")
		
		self.fail_publisher.publish_many(payloads)	
		count = 0
		for redis_id in redis_ids:
			if redis_ids == "N/A":
				self.logger.error("This message contains no redis_id, malformed message. Leaving in pending")
				continue
			count +=1
			self.message_consumer.acknowledge(redis_id)
   
		self.logger.info(f"{count} messages acknowledged and moved to failure stream.")
  
	def _parse_message(self, raw_msg: Dict[str, Any]) -> Optional[StreamMessage]:
		"""Converts raw Redis dict to a typed StreamMessage with a nested Pydantic model."""
		msg_data = raw_msg.get("data", {})

		try:
			# Pydantic does the heavy lifting of validation and parsing!
			parsed_message:Message = Message.model_validate(msg_data)

			# Calculate priority based on the validated object
			msg_type:str = parsed_message.header.type
			priority = PRIORITY_MAP.get(msg_type, LOWEST_PRIORITY)

			return StreamMessage(
				stream=raw_msg["stream"],
				redis_id=raw_msg["redis_message_id"],
				data=parsed_message,  
				priority=priority
			)
   
		except ValidationError as e:
			self.logger.error(f"Pydantic validation failed for message {raw_msg['redis_message_id']}: {e}")
			self._handle_failure(raw_msg, e)
			return None
	
	@abstractmethod
	def _process_message(self, message: StreamMessage) -> StreamMessage:
		pass

	def _process_and_publish_worker(self, message: StreamMessage) -> Tuple[str, str]:
		"""Worker for concurrent mode. Processes, then publishes."""
		try:
			processed_message:StreamMessage = self._process_message(message)
			new_redis_id = self.success_publish_router.publish_one(processed_message.data)
   
			if not new_redis_id:
				raise ProcessingError("Publisher returned an empty ID.")
			
			self.message_consumer.acknowledge(message.redis_id)
			return message.redis_id, new_redis_id

		except Exception as e:
			# Catch any exception, including ProcessingError, and route to failure.
			self._handle_failure(message, e)
			# Raise it again so as_completed knows the future failed
			raise
	
	def _process_batch_sequentially(self, raw_messages: List[Dict[str, Any]]) -> None:
		self.logger.info(f"Fetched {len(raw_messages)} messages. Processing...")
  
		stream_messages: List[StreamMessage] = [msg for m in raw_messages if (msg := self._parse_message(m))]
		payloads_to_publish: List[Dict[str, Any]] = []
		payload_to_message_map: Dict[int, StreamMessage] = {}
  
		for message in stream_messages:
			try:
				processed_message = self._process_message(message)
				payload = processed_message.data.model_dump()
            
				# Store the mapping
				payload_to_message_map[id(payload)] = message 
				payloads_to_publish.append(payload)
    
			except Exception as e:
				self._handle_failure(message, e)

		if not payloads_to_publish:
			self.logger.info("No messages were successfully processed to be published.")
			return

		publish_results = self.success_publish_router.publish_many(payloads_to_publish)
		ack_count = 0
		failure_count = 0
		unroutable_payloads = publish_results.get("unroutable", [])
		unroutable_payload_ids = {id(p) for p in unroutable_payloads}
		
		for payload_id, original_message in payload_to_message_map.items():
			if payload_id in unroutable_payload_ids:
				self._handle_failure(
					original_message, 
					RoutingError("Message was unroutable; no valid key in routing map")
				)
				failure_count += 1
			else:
				# This message was successfully published. Acknowledge it.
				self.message_consumer.acknowledge(original_message.redis_id)
				ack_count += 1
		
		if ack_count > 0:
			self.logger.info(f"Successfully published and acknowledged {ack_count} routable messages.")
		
		if failure_count > 0:
			# The logging for this is handled inside _handle_failure, 
			# but a summary log is good practice.
			self.logger.info(f"Handled {failure_count} unroutable messages by sending to failure stream.")


	def _process_batch_concurrently(self, executor: ThreadPoolExecutor, raw_messages: List[Dict[str,Any]]):
		self.logger.info(f"Fetched {len(raw_messages)} messages. Processing...")
		stream_messages = [msg for m in raw_messages if (msg := self._parse_message(m))]

		future_to_message = {
			executor.submit(self._process_and_publish_worker, msg): msg for msg in stream_messages
		}

		for future in as_completed(future_to_message):
			original_message = future_to_message[future] 

			try:
				old_redis_id, new_redis_id = future.result() 
				self.logger.debug(f"Successfully published Msg {old_redis_id} -> {new_redis_id}")
			except Exception:
				self.logger.warning(f"A worker for message {original_message.redis_id} failed. See previous error logs for details.")
 
	def _get_raw_messages(self) -> List[Dict[str,Any]]:
		"""Blocks until messages are available, then returns a batch."""
		while self.keep_running:
			raw_messages = self.message_consumer.consume_many(num_to_consume=self.batch_size, block=2000)
			if raw_messages:
				return raw_messages
			self.logger.debug("No new messages, waiting...")
		return [] 
	
	def _process_a_batch(self, executor: Optional[ThreadPoolExecutor]):
		"""Fetches and processes a single batch of messages, either pending or new."""
		# Prioritize pending messages from previous runs
		raw_messages = self.message_consumer.consume_pending()
		if not raw_messages:
			raw_messages = self._get_raw_messages()

		if not raw_messages:
			return
		self.logger.info(f"Processing batch of {len(raw_messages)} messages.")
		if self.is_concurrent:
			self._process_batch_concurrently(executor, raw_messages)
		else:
			self._process_batch_sequentially(raw_messages)

 
	def run(self):
		"""Main execution loop for the service."""
		self.logger.info(f"Service '{self.__class__.__name__}' started. Listening on {self.input_stream}.")
		self.logger.info(f"Mode: {'Concurrent' if self.is_concurrent else 'Sequential'}.")

		executor = ThreadPoolExecutor(max_workers=self.max_workers) if self.is_concurrent else None
		
		with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
			if not self.is_concurrent:
				executor = None # Don't use the executor in sequential mode
			try:
				while self.keep_running:
					self._process_a_batch(executor)
			except Exception as e:
				self.logger.critical(f"Unexpected critical error in main loop: {e}", exc_info=True)
			finally:
				self.logger.info("Service shutting down.")
