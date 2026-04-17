
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from logging import Logger, getLogger
from typing import Any, Dict, List, Optional, Tuple

from pydantic import ValidationError

from common.models.api.dtos.job import JobType
from common.models.api.redis_models import Message, StreamMessage
from common.redis_client.consumer_combiner import RedisConsumerCombiner
from common.redis_client.prioritised_consumer_combiner import BlockPrioritisationLevel, PrioritisedRedisConsumerCombiner
from common.redis_client.publisher import RedisPublisher
from common.redis_client.publisher_router import RedisPublisherRouter

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
        output_streams:List[str]
        router_key_values:List[str]
        group_name:str
        consumer_name:str
        block_prioritisation_level:BlockPrioritisationLevel
        failure_output_stream: str | None # if none, then failed batches will just not be published and will be pending for next cycle
        routing_key:List[str] = field(default_factory=lambda: ["header", "type"])
        is_concurrent: bool = False
        max_workers:int = 1
        batch_size:int = 10
        is_cut_and_paste_mode: bool = True
        retry_failure_mode: bool = False

        

class ServiceTemplate(ABC):
	"""Concurrently scrapes, parses, and publishes messages"""

	def __init__(self, config: ServiceConfig ) -> None:
		self.logger: Logger = getLogger(config.service_name)
		self.max_workers = config.max_workers
		self.batch_size = config.batch_size
		self.keep_running: bool = True
		self.is_concurrent = config.is_concurrent

		# will fetch from failure stream if truly no jobs exist in user or background
		if config.retry_failure_mode:
			config.input_streams.append(config.failure_output_stream)
  
		if config.input_streams:
			self.input_streams = config.input_streams
			stream_to_priority_map = PrioritisedRedisConsumerCombiner.generate_stream_to_priority_mapping(config.input_streams)
			stream_to_block_map = PrioritisedRedisConsumerCombiner.generate_stream_to_block_mapping(input_streams=config.input_streams, level=config.block_prioritisation_level)
			self.message_consumer = PrioritisedRedisConsumerCombiner(
				stream_to_priority_map=stream_to_priority_map,
				stream_to_block_map=stream_to_block_map,
				group_name=config.group_name, 
				consumer_name=config.consumer_name
			)
   
		if config.output_streams:
			self.output_streams = config.output_streams
			routing_map = RedisPublisherRouter.generate_router_mapping(config.output_streams, config.router_key_values)
			self.success_publish_router = RedisPublisherRouter(
				routing_key=config.routing_key, routing_map=routing_map
			)

		if config.failure_output_stream:
			self.failure_output_stream = config.failure_output_stream
			self.fail_publisher = RedisPublisher(config.failure_output_stream)
   
		self.is_cut_and_paste_mode = config.is_cut_and_paste_mode

	def shutdown(self, *args) -> None:
		"""Signal handler to initiate a graceful shutdown."""
		self.logger.info("\nShutdown signal received. Finishing current batch...")
		self.keep_running = False

	def _handle_failure(self, message: StreamMessage | Dict[str, Any], error: Exception):
		"""Logs the error and publishes the message to the failure stream."""
		is_stream_message:bool = isinstance(message, StreamMessage)
		# self.logger.debug(message)
	
		redis_id = message.redis_id if is_stream_message else message.get("redis_message_id", "N/A")
		stream_name = message.stream if is_stream_message else message.get("stream", "N/A")
		self.logger.error(f"Failed to process message {redis_id}: {error}")

		payload = message.data.model_dump(mode='json') if is_stream_message else message.get("data", {})
  		# Acknowledge the original message before publishing to failure queue
		self.fail_publisher.publish_one(payload)

		if self.is_cut_and_paste_mode:
			self.message_consumer.acknowledge_and_delete(stream_name=stream_name, redis_message_id=redis_id)
		else:
			self.message_consumer.acknowledge(stream_name=stream_name, redis_message_id=redis_id)
  
	def _handle_failure_batch(self, messages: List[StreamMessage | Dict[str, Any]], error: Exception):
		"""Logs the error and publishes the message to the failure stream."""
		if not messages:
			self.logger.error("No messages to handle failure")
			return
		self.logger.error(f"Failed to process batch of {len(messages)} messages: {error}")
  
		for message in messages:
			self._handle_failure(message, error)
  
	def _parse_message(self, raw_msg: Dict[str, Any]) -> Optional[StreamMessage]:
		"""Converts raw Redis dict to a typed StreamMessage with a nested Pydantic model."""
		msg_data = raw_msg.get("data", {})

		try:
			# Pydantic does the heavy lifting of validation and parsing!
			parsed_message:Message = Message.model_validate(msg_data)

			# Calculate priority based on the validated object
			msg_type:str = parsed_message.header.type
			#temp
			priority = 0

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
			payload = processed_message.data.model_dump(mode='json')
			new_redis_id = self.success_publish_router.publish_one(payload)
   
			if not new_redis_id:
				raise ProcessingError("Publisher returned an empty ID.")

			if self.is_cut_and_paste_mode:
				self.message_consumer.acknowledge_and_delete(message.stream, message.redis_id)
			else:
				self.message_consumer.acknowledge(message.stream, message.redis_id)
				
			return message.redis_id, new_redis_id

		except Exception as e:
			# Catch any exception, including ProcessingError, and route to failure.
			self._handle_failure(message, e)
			# Raise it again so as_completed knows the future failed
			raise
	
	def _process_batch_sequentially(self, raw_messages: List[Dict[str, Any]]) -> None:
  
		stream_messages: List[StreamMessage] = [msg for m in raw_messages if (msg := self._parse_message(m))]
		payloads_to_publish: List[Dict[str, Any]] = []
		payload_to_message_map: Dict[int, StreamMessage] = {}
  
		for message in stream_messages:
			try:
				processed_message = self._process_message(message)
				payload = processed_message.data.model_dump(mode='json')

				# Store the mapping
				payload_to_message_map[id(payload)] = message 
				payloads_to_publish.append(payload)
    
			except Exception as e:
				self._handle_failure(message, e)

		if not payloads_to_publish:
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
				if self.is_cut_and_paste_mode:
					self.message_consumer.acknowledge_and_delete(original_message.stream, original_message.redis_id)
				else:
					self.message_consumer.acknowledge(message.stream, original_message.redis_id)

				ack_count += 1
		
		if failure_count > 0:
			self.logger.warning(f"Sent {failure_count} unroutable messages to failure stream.")

	def _process_batch_concurrently(self, executor: ThreadPoolExecutor, raw_messages: List[Dict[str,Any]]):
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
			raw_messages = self.message_consumer.consume_many(num_to_consume=self.batch_size)
			if raw_messages:
				return raw_messages
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
		self.logger.info(f"Service '{self.__class__.__name__}' started. Listening on {self.input_streams}.")
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
