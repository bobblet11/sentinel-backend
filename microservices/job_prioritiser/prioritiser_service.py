import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List
from logging import Logger, getLogger
from common.redis_client.consumer_combiner import RedisConsumerCombiner
from common.redis_client.publisher import RedisPublisher
from common.models.api.redis_models import StreamMessage
from dataclasses import dataclass

from .config import (
    BATCH_SIZE,
    CONSUMER_NAME,
    GROUP_NAME,
    INPUT_STREAMS,
    LOWEST_PRIORITY,
    MAX_PUBLISH_WORKERS,
    OUTPUT_STREAM,
    PRIORITY_MAP,
)

class PrioritiserService:

    def __init__(self):
        self.logger: Logger = getLogger("prioritiser")
        self.keep_running = True
        self.combiner = RedisConsumerCombiner(
            streams=INPUT_STREAMS, group_name=GROUP_NAME, consumer_name=CONSUMER_NAME
        )
        self.publisher = RedisPublisher(stream_name=OUTPUT_STREAM)

    def shutdown(self) -> None:
        """Signal handler to initiate a graceful shutdown."""
        self.logger.info("\nShutdown signal received. Finishing current batch...")
        self.keep_running = False

    def _parse_message(self, raw_msg: Dict[str, Any]) -> StreamMessage:
        """Converts raw Redis dict to a typed Dataclass and calculates priority."""
        msg_data = raw_msg.get("data", {})
        msg_type = msg_data.get("header", {}).get("type")
        
        # Calculate priority once during parsing
        priority = PRIORITY_MAP.get(msg_type, LOWEST_PRIORITY)
        
        return StreamMessage(
            stream=raw_msg["stream"],
            redis_id=raw_msg["redis_message_id"],
            data=msg_data,
            priority=priority
        )
    
    def _process_batch(self, raw_messages: List[Dict[str, Any]]) -> int:
        # 2. Parse and Prioritize
        self.logger.info(f"Fetched {len(raw_messages)} messages. Prioritising...")
        parsed_messages: List[StreamMessage] = [self._parse_message(m) for m in raw_messages]
        parsed_messages.sort(key=lambda m: m.priority)
        
        
        self.logger.info(f"Publishing {len(parsed_messages)} messages concurrently...")

        # 3. Publish and Ack
        total_count:int = len(parsed_messages)
        success_count:int = 0
        
        if parsed_messages:
            parsed_message_data: List[Dict, Any] = [message.data for message in parsed_messages]
            published_ids: List[str] = self.publisher.publish_many(parsed_message_data)
            if published_ids:
                ack_count = 0
            
            for original_msg in parsed_messages:
                self.combiner.acknowledge(original_msg.stream, original_msg.redis_id)
                ack_count += 1
            
            self.logger.info(
                f"Batch Complete: Published and Acked {ack_count} messages."
            )
        else:
            self.logger.error(
                "Batch Publish Failed. RedisPublisher returned None. "
                "Messages will NOT be acknowledged and will be re-delivered."
            )
    
        percentage:float = success_count/total_count if total_count > 0 else 0
        self.logger.info(f"  - Successfully published and acknowledged {success_count} / {total_count} ({percentage:.1f}%)")

    def run(self) -> None:
        """
        Main execution loop. Fetches and processes messages sequentially.
        """
        self.logger.info(f"Service started. Listening on {INPUT_STREAMS}")

        while self.keep_running:
            try:
                
                # 0. Check & deal with pending messagess
                self.logger.info(f"Checking for pending messages...")
                pending_messages = self.combiner.consume_pending()

                if pending_messages:
                    self.logger.info(f"Found {len(pending_messages)} pending messages. Processing them...")
                    self._process_batch(pending_messages)

                
                # 1. Fetch
                self.logger.info(f"Waiting for up to {BATCH_SIZE} messages...")
                raw_messages:List[Dict[str, Any]] = self.combiner.consume_many(
                    num_to_consume=BATCH_SIZE, block=2000
                )
                if not raw_messages:
                    continue
                
                self._process_batch(raw_messages)
               
            except Exception as e:
                self.logger.error(f"Unexpected error in main loop {e}")
                self.shutdown()
                
        self.logger.info("SHUTTING DOWN")
