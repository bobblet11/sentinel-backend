# microservices/nlp/nlp_service.py
from concurrent.futures import ThreadPoolExecutor, as_completed
from logging import Logger, getLogger
import time
from typing import Any, Dict, Optional, List, Tuple
from common.models.api.redis_models import StreamMessage
from common.redis_client.consumer import RedisConsumer
from common.redis_client.publisher import RedisPublisher
from common.redis_client.publisher_router import RedisPublisherRouter
from microservices.nlp.config import BACKGROUND_OUTPUT_STREAM, BATCH_SIZE, FAILURE_OUTPUT_STREAM, INPUT_STREAM, GROUP_NAME, CONSUMER_NAME, NLP_MAX_WORKERS, USER_OUTPUT_STREAM
from microservices.nlp.types import ArticleInput, AnalysisResult, AnalysisOptions
from microservices.nlp.models.base import NLPComponent

# We will implement these empty skeletons in the next step
from microservices.nlp.components.preprocess import Preprocessor
from microservices.nlp.components.centrality import CentralityScorer
from microservices.nlp.components.bias import BiasDetector
from microservices.nlp.components.ner import EntityRecognizer
from microservices.nlp.components.checkworthy import ClaimExtractor

PRIORITY_MAP = {
    "user": 1,
    "admin": 1,  
    "background": 2,
    "logging": 3,
}
LOWEST_PRIORITY: float = float("inf")

class SentinelNLP:
    routing_map = {"user": USER_OUTPUT_STREAM, "background": BACKGROUND_OUTPUT_STREAM}

    def __init__(self, options: Optional[AnalysisOptions] = None):
        
        self.logger: Logger = getLogger("nlp_service")
        self.keep_running = True
        self.message_consumer = RedisConsumer(
            stream_name=INPUT_STREAM,
            group_name=GROUP_NAME, 
            consumer_name=CONSUMER_NAME
        )
        self.sucess_publisher = RedisPublisherRouter(
            routing_key=["header","type"], routing_map=self.routing_map
        )
        self.fail_publisher = RedisPublisher(FAILURE_OUTPUT_STREAM)
        
        self.default_options = options or AnalysisOptions()
        
        # Define the execution order of the pipeline
        self.pipeline: List[NLPComponent] = [
            Preprocessor(),
            CentralityScorer(),
            BiasDetector(),
            EntityRecognizer(),
            ClaimExtractor()
        ]

    def shutdown(self, *args) -> None:
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

    def _publish_and_ack_worker(
        self, message: StreamMessage, publisher: RedisPublisherRouter | RedisPublisher
    ) -> Tuple[str,str]:
        """
        The "worker" function for a single thread.
        It publishes one message and, if successful, acknowledges it.
        """

        try:
            redis_id_of_new_message:str = publisher.publish_one(message.data)
            self.message_consumer.acknowledge(message.redis_id)
            return message.redis_id, redis_id_of_new_message
        except Exception as e:
            self.logger.error(f"Worker failed to publish or acknowlesdge message {message.redis_id}: {e}")
            raise e
        
    def analyze(self, article: ArticleInput, options: Optional[AnalysisOptions] = None) -> AnalysisResult:
        """
        The main orchestrator that passes the article through each pipeline stage.
        """
        current_options = options or self.default_options
        
        # Initialize the result container
        result = AnalysisResult(article_id=article.id)
        result.status = "processing"

        # Execute each stage sequentially
        for component in self.pipeline:
            try:
                # Components modify 'result' in-place (e.g. adding claims or entities)
                component.run(article, result, current_options)
            except Exception as e:
                # Log the error but allow the rest of the pipeline to attempt completion
                print(f"Pipeline error in {component.__class__.__name__}: {str(e)}")
                continue

        result.status = "completed"
        return result

    
    
    #replace this function with your code
    def _process_message(self, message: StreamMessage) -> Tuple[str,str]:
        pass
        try:
            #each step of pipeline here? take out data needed from message via stream message object, and pass thru analyze?
            fetched_message:StreamMessage = self._fetch_article_and_update(message)
            parsed_message:StreamMessage = self._parse_article_and_update(fetched_message)
            return self._publish_and_ack_worker(parsed_message, self.sucess_publisher)
        
        # This is error 1 from scraper. you can replace it with error raised due to centrality
        except FailedToFetch as e:
            return self._publish_and_ack_worker(message, self.fail_publisher)
        # This is error 1 from scraper. you can replace it with error raised due to step AFTER centrality
        except FailedToParse as e:
            return self._publish_and_ack_worker(message, self.fail_publisher)
        # Add all other errors below.
    
    def _process_batch(self, executor: ThreadPoolExecutor, raw_messages: List[Dict[str,Any]]):
        
        stream_messages: List[StreamMessage] = [self._parse_message(m) for m in raw_messages]
        
        processed_message_futures = {
            executor.submit(self._process_message, msg): msg for msg in stream_messages
        }

        for future in as_completed(processed_message_futures):
            original_message = processed_message_futures[future] 

            try:
                old_redis_id, new_redis_id = future.result() 
                self.logger.debug(f"Successfully published Msg {old_redis_id} -> {new_redis_id}")
            except Exception:
                self.logger.error(f"Could not process message {original_message.redis_id}. Message was acknowledged and placed in the failure queue")
    
    
    def run(self):
        """
        Main execution loop. Fetches and processes messages concurrently.
        """
        self.logger.info(f"Service started. Listening on {INPUT_STREAM}")
        
        with ThreadPoolExecutor(max_workers=NLP_MAX_WORKERS) as executor:
            while self.keep_running:
                try:
                    # 0. Check & deal with pending messagess
                    self.logger.info(f"Checking for pending messages...")
                    pending_messages:List[Dict[str, Any]] = self.message_consumer.consume_pending()
                    if pending_messages:
                        self.logger.info(f"Found {len(pending_messages)} pending messages. Processing them...")
                        self._process_batch(executor, pending_messages)

                    
                    # 1. Fetch
                    self.logger.info(f"Waiting for up to {BATCH_SIZE} messages...")
                    raw_messages:List[Dict[str, Any]] = []
                    while True:
                        raw_messages = self.message_consumer.consume_many(
                            num_to_consume=BATCH_SIZE, block=2000
                        )   
                        if not raw_messages:
                            time.sleep(2)
                            continue
                        break
                    
                    self.logger.info(f"Found {len(raw_messages)} messages. Processing them...")
                    self._process_batch(executor, raw_messages)
                    
                except Exception as e:
                    self.logger.error(f"Unexpected error in main loop {e}")
                    self.shutdown()
                
        self.logger.info("SHUTTING DOWN")
        