import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict

from common.redis_client.consumer import RedisConsumer
from common.redis_client.publisher import RedisPublisher
from common.redis_client.publisher_router import RedisPublisherRouter
from microservices.web_scraper.config import (
    BACKGROUND_OUTPUT_STREAM,
    BATCH_SIZE,
    CONSUMER_NAME,
    FAILURE_OUTPUT_STREAM,
    GROUP_NAME,
    INPUT_STREAM,
    SCRAPER_MAX_WORKERS,
    USER_OUTPUT_STREAM,
)
from microservices.web_scraper.managers.fetch_manager import fetch_manager


class ScraperService:
    """ """

    routing_map = {"user": USER_OUTPUT_STREAM, "background": BACKGROUND_OUTPUT_STREAM}

    def __init__(self):
        print("Initializing Redis clients...")
        self.name = type(self).__name__
        self.consumer = RedisConsumer(INPUT_STREAM, GROUP_NAME, CONSUMER_NAME)
        self.successful_publisher = RedisPublisherRouter(
            routing_key="type", routing_map=self.routing_map
        )
        self.failure_publisher = RedisPublisher(FAILURE_OUTPUT_STREAM)
        self.keep_running = True

    def run(self):
        """
        Main execution loop. Fetches and processes messages concurrently.
        """
        with ThreadPoolExecutor(max_workers=SCRAPER_MAX_WORKERS) as executor:

            print(f"[{datetime.datetime.now()}] Checking for pending messages...")
            pending_messages = self.consumer.consume_pending()

            if pending_messages:

                print(
                    f"[{datetime.datetime.now()}] Found {len(pending_messages)} pending messages. Processing them..."
                )

                self.process_messages(executor, pending_messages)

            while self.keep_running:

                print(
                    f"[{datetime.datetime.now()}] Waiting for up to {BATCH_SIZE} messages..."
                )

                messages = self.consumer.consume_many(
                    num_to_consume=BATCH_SIZE, block=0
                )

                if not messages:
                    continue

                print(f"--> Fetched {len(messages)} messages. Processing...")
                self.process_messages(executor, messages)

        print(f"[{self.name}] SHUTTING DOWN")

    def shutdown(self, signum, frame):
        """Signal handler to initiate a graceful shutdown."""

        print("\nShutdown signal received. Finishing current batch...")
        self.keep_running = False

    def process_messages(self, executor, messages):
        # --- Concurrent Processing ---
        future_to_message = {
            executor.submit(self.process_message, msg): msg for msg in messages
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
            except Exception:
                print(
                    f"  - Final failure for Msg ID {redis_msg_id}. It was NOT acknowledged and will be retried by another consumer later."
                )

    def process_message(self, message):

        fetched_message = self._attempt_fetch_article(message)

        if not fetched_message:
            print("Failed to Fetch!!!")
            return self._publish_and_ack_worker(message, self.failure_publisher)

        parsed_message = self._attempt_parse_article(fetched_message)

        if not parsed_message:
            print("Failed to Parse!!!")
            return self._publish_and_ack_worker(fetched_message, self.failure_publisher)

        return self._publish_and_ack_worker(parsed_message, self.successful_publisher)

    def _publish_and_ack_worker(
        self, message: Dict[str, Any], publisher: RedisPublisherRouter | RedisPublisher
    ) -> Dict[str, Any]:
        """
        The "worker" function for a single thread.
        It publishes one message and, if successful, acknowledges it.
        This function must be self-contained and handle its own errors.
        """
        return message
        stream = message["stream"]
        redis_msg_id = message["redis_message_id"]
        message_data = message["data"]

        try:
            if not publisher.publish_one(message_data):
                raise RuntimeError(
                    f"Failed to publish message {redis_msg_id} to stream"
                )

            self.consumer.acknowledge(stream, redis_msg_id)

            return message
        except Exception as e:
            print(f"  [ERROR] Worker failed for message {redis_msg_id}: {e}")
            raise e

    def _attempt_fetch_article(self, message):

        try:
            url = message.get("data", {}).get("data", {}).get("url", None)
            if not url:
                print(message)
            print(f"Attemping to fetch from {url}")
            page_html = fetch_manager.fetch_article_html(url)
            print(f"-> SUCCESS: Received HTML for {url}, length: {len(page_html)}")
            updated_message = message.copy()
            updated_message["data"]["payload"]["html"] = page_html
            return updated_message
        except Exception:
            print(f"\n[!!!] ULTIMATE FAILURE to fetch {url} after all retries.")
            return None

    def _attempt_parse_article(self, message):
        return message
