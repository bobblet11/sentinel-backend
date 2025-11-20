import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict

from common.redis_client.consumer_combiner import RedisConsumerCombiner
from common.redis_client.publisher import RedisPublisher

from .config import (
    BATCH_SIZE,
    CONSUMER_NAME,
    GROUP_NAME,
    INPUT_STREAMS,
    LOWEST_PRIORITY,
    MAX_WORKERS,
    OUTPUT_STREAM,
    PRIORITY_MAP,
)

# message_dict = {
#     'stream': stream_name.decode('utf-8'),
#     'redis_message_id': redis_message_id.decode('utf-8'),
#     'data': message_data
# }


class PrioritiserService:

    def __init__(self):
        """Initializes the service, clients, and shutdown flag."""
        self.keep_running = True
        print("Initializing Redis clients...")
        self.combiner = RedisConsumerCombiner(
            streams=INPUT_STREAMS, group_name=GROUP_NAME, consumer_name=CONSUMER_NAME
        )
        self.publisher = RedisPublisher(stream_name=OUTPUT_STREAM)

    def shutdown(self, signum, frame):
        """Signal handler to initiate a graceful shutdown."""
        print("\nShutdown signal received. Finishing current batch...")
        self.keep_running = False

    def prioritize_messages(self, messages: list) -> list:
        """
        Sorts a list of message dictionaries based on the PRIORITY_MAP.
        """

        def get_priority(message):
            message_type = message.get("data", {}).get("header", {}).get("type")
            return PRIORITY_MAP.get(message_type, LOWEST_PRIORITY)

        return sorted(messages, key=get_priority)

    def publish_and_ack_worker(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        The "worker" function for a single thread.
        It publishes one message and, if successful, acknowledges it.
        This function must be self-contained and handle its own errors.
        """

        stream = message["stream"]
        redis_msg_id = message["redis_message_id"]
        message_data = message["data"]

        try:
            if not self.publisher.publish_one(message_data):
                raise RuntimeError(
                    f"Failed to publish message {redis_msg_id} to stream {OUTPUT_STREAM}"
                )

            self.combiner.acknowledge(stream, redis_msg_id)

            return message
        except Exception as e:
            print(f"  [ERROR] Worker failed for message {redis_msg_id}: {e}")
            raise e

    def run(self):
        """
        Main execution loop. Fetches and processes messages concurrently.
        """
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:

            while self.keep_running:
                print(
                    f"[{datetime.datetime.now()}] Waiting for up to {BATCH_SIZE} messages..."
                )

                messages = self.combiner.consume_many(
                    num_to_consume=BATCH_SIZE, block=0
                )

                if not messages:
                    continue

                print(f"--> Fetched {len(messages)} messages. Prioritizing...")
                prioritized_messages = self.prioritize_messages(messages)
                print(
                    f"--> Publishing {len(prioritized_messages)} messages concurrently..."
                )

                # --- Concurrent Processing ---
                future_to_message = {
                    executor.submit(self.publish_and_ack_worker, msg): msg
                    for msg in prioritized_messages
                }

                # Process results as they are completed
                for future in as_completed(future_to_message):
                    original_message = future_to_message[future]
                    redis_msg_id = original_message["redis_message_id"]
                    try:
                        future.result()
                        print(
                            f"  - Successfully published and acknowledged Msg ID {redis_msg_id}"
                        )
                    except Exception as e:
                        print(
                            f"  - Final failure for Msg ID {redis_msg_id}. It was NOT acknowledged and will be retried by another consumer later."
                        )

        print("SHUTTING DOWN")
