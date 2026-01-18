import time
from typing import Any, Dict, List
from logging import Logger, getLogger
from common.redis_client.consumer_combiner import RedisConsumerCombiner
from common.redis_client.publisher import RedisPublisher
from common.models.api.redis_models import StreamMessage
from dataclasses import dataclass

from common.service.service_template import RoutingError, ServiceConfig, ServiceTemplate



PRIORITY_MAP = {
    "user": 1,
    "admin": 1,  
    "background": 2,
    "logging": 3,
}
LOWEST_PRIORITY: float = float("inf")
SERVICE_NAME="prioritiser"

class PrioritiserService(ServiceTemplate):
    """Sequentially prioritises messages based on whether they are user or background jobs"""
    def __init__(self, config:ServiceConfig) -> None:
        super().__init__(config)
    
    def _process_message(self, message: StreamMessage) -> StreamMessage:
        # The "processing" for this service is a no-op on individual messages.
        # The main logic is in the overridden batch method.
        return message

    def _process_batch_sequentially(self, raw_messages: List[Dict[str, Any]]):
        stream_messages: List[StreamMessage] = [msg for m in raw_messages if (msg := self._parse_message(m))]
        try:
            stream_messages.sort(key=lambda m: m.priority)
        except Exception as e:
            #entire batch fails
            self._handle_failure_batch(stream_messages, e)
            return

        payloads_to_publish: List[Dict[str, Any]] = []
        payload_to_message_map: Dict[int, StreamMessage] = {}

        for msg in stream_messages:
            payload = msg.data.model_dump()
            payload_to_message_map[id(payload)] = msg 
            payloads_to_publish.append(payload)

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
                self.message_consumer.acknowledge(original_message.redis_id)
                ack_count += 1

        if ack_count > 0:
            self.logger.info(f"Successfully published and acknowledged {ack_count} routable messages.")

        if failure_count > 0:
            self.logger.info(f"Handled {failure_count} unroutable messages by sending to failure stream.")
