import datetime
import hashlib
import logging

from common.models.api.dtos.job import JobStage, JobStatus, JobType
from common.models.api.redis_models import Article, Message, MessageHeader, MessagePayload, MessageTimestamp, add_timestamp_to_message
from common.redis_client.duplicate_filter import RedisDuplicateFilter
from common.redis_client.publisher import RedisPublisher
from common.io.json_updater import JsonHandler
from microservices.ingestor.config import OUTPUT_STREAM, REDIS_DUPLICATE_FILTER_KEY
from dataclasses import dataclass
from typing import Iterator, Dict, Set, List, Any
from datetime import datetime, timezone
class BaseIngestor:
    """
    A base class that defines the template for an ingestion workflow.
    Subclasses must implement the `_fetch_articles` generator method.
    """

    def __init__(self, duplicate_filter = None, publisher = None):
        # If no duplicate_filter was provided, create the default one NOW.
        if duplicate_filter is None:
            self.duplicate_filter = RedisDuplicateFilter(REDIS_DUPLICATE_FILTER_KEY, ttl_s=None)
        else:
            self.duplicate_filter = duplicate_filter

        # Do the exact same thing for the publisher.
        if publisher is None:
            self.publisher = RedisPublisher(OUTPUT_STREAM)
        else:
            self.publisher = publisher
            
        self.logger: logging.Logger = logging.getLogger("base_ingestor")
        self.stats_json_handler = JsonHandler(filename="stats.json")

    def _log_stats(self, new:int, seen:int, total:int) -> None:
        file_data = self.stats_json_handler.read_json()
        
        current_date = str(datetime.now().date())
        entry = {
            "new": new,
            "seen": seen,
            "total_processed": total
        }
        
        existing_entry:Dict[str,Any] = file_data.get(current_date, None)
        if existing_entry:
            entry["new"] += existing_entry.get("new", 0)
            entry["seen"] += existing_entry.get("seen", 0)
            entry["total_processed"] += existing_entry.get("total_processed", 0)

        file_data[current_date] = entry
        
        self.stats_json_handler.write_json(file_data)
        
    
    def fetch_articles(self) -> Iterator[Article]: 
        """
        Generator that fetches URLs from some source.

        This method must be a generator that yields Articles, where each
        Article represents a single fetched article and must contain at least
        a "link".

        Example: yield {"link": "http://a.com", "source": "BBC"}
        """

        raise NotImplementedError("Please Implement this method")

    def run(self) -> None:
        """
        Main cycle of ingestor service. Fetches, Filters, and Publishes articles from source of urls.
        """

        # Step 1: Fetch articles from source
        self.logger.info("--- Starting new ingestion cycle ---")
        raw_articles: List[Article] = list(self.fetch_articles())
        if len(raw_articles) == 0:
            self.logger.info("--- Ingestion cycle finished. No articles found. ---\n\n")
            return
        
        # Step 2: Check if url has already been seen
        article_urls: List[str] = [a.link for a in raw_articles if a.link]
        unique_urls: Set[str] = set(article_urls)
        if not unique_urls:
            self.logger.info("--- Ingestion cycle finished. No valid URLs found. ---\n\n")
            return
        
        # Step 3: Filter out articles that haven't been seen
        unseen_urls: List[str] = self.duplicate_filter.has_many(list(unique_urls))
        if not unseen_urls:
            self.logger.info("--- Ingestion cycle finished. Seen all articles already. ---\n\n")
            return
        
        unseen_urls_set: Set[str] = set(unseen_urls)
        unseen_articles: List[Article] = []
        for article in raw_articles:  # Preserve original order
            if article.link in unseen_urls_set:
                unseen_articles.append(article)
                unseen_urls_set.remove(article.link)  # Only first occurrence
            if not unseen_urls_set:
                break
                        
        # Step 4: Publish unseen articles
        messages_to_publish: List[Any] = []
        for article in unseen_articles:
            payload = MessagePayload(article_url=article.link, news_outlet=article.source, title=article.title, summary=article.summary)
            job_uid = hashlib.md5(article.link.encode()).hexdigest()[:36]
            message = Message(
                header=MessageHeader(
                    id=None,
                    uid=job_uid,
                    created_at=datetime.now().isoformat(),
                    status=JobStatus.PENDING.value,
                    type=JobType.BACKGROUND.value,
                ),
                payload=payload,
                stage_timestamps=[]
            )
            
            message = add_timestamp_to_message(message=message, stage_name=JobStage.INGESTED)
            messages_to_publish.append(message.model_dump())

        if len(messages_to_publish) == 0:
            self.logger.info(
                "--- Ingestion cycle finished. Cannot publish for some reason. ---\n\n"
            )
            return

        published_ids:List[str] = self.publisher.publish_many(messages_to_publish)
        if not published_ids == 0:
            self.logger.info("--- Ingestion cycle finished. Could not publish to queue. ---\n\n")
            return

        # Step 5: Add urls to cache for future cycles
        self.duplicate_filter.add_many(unseen_urls)
        
        new_count = len(unseen_articles)
        seen_this_cycle = len(unique_urls) - len(unseen_urls)
        total_fetched = len(raw_articles)
        
        self._log_stats(new_count, seen_this_cycle, total_fetched)
        
        self.logger.info("--- Ingestion cycle finished ---")
        self.logger.info(f"\tNew this cycle: {new_count}")
        self.logger.info(f"\tSeen this cycle: {seen_this_cycle}")
        self.logger.info(f"\tTotal fetched: {total_fetched} (unique URLs: {len(unique_urls)})")
        self.logger.info(f"\tRedis total cached: {self.duplicate_filter.client.scard(self.duplicate_filter.key_name)}")
        self.logger.info("-" * 10)
