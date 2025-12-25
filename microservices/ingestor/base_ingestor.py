import datetime
import hashlib
import logging

from common.models.api.redis_models import Message, MessageHeader, MessageURLPayload
from common.redis_client.duplicate_filter import RedisDuplicateFilter
from common.redis_client.publisher import RedisPublisher
from microservices.ingestor.config import OUTPUT_STREAM, REDIS_DUPLICATE_FILTER_KEY
from dataclasses import dataclass
from typing import Iterator, Dict, Set, List, Any


@dataclass(frozen=True)
class Article:
    link: str
    source: str = "Unknown Source"
    
class BaseIngestor:
    """
    A base class that defines the template for an ingestion workflow.
    Subclasses must implement the `_fetch_articles` generator method.
    """

    def __init__(self):
        self.duplicate_filter = RedisDuplicateFilter(REDIS_DUPLICATE_FILTER_KEY)
        self.publisher = RedisPublisher(OUTPUT_STREAM)
        self.logger: logging.Logger = logging.getLogger("base_ingestor")

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
        unique_articles: Set[Article] = set([a for a in raw_articles if a.link])
        if len(unique_articles) == 0:
            self.logger.info("--- Ingestion cycle finished. No articles found. ---\n\n")
            return
        
        # Step 2: Check if url has already been seen
        article_urls: List[str] = [article.link for article in unique_articles]
        unseen_article_urls: List[str] = self.duplicate_filter.has_many(article_urls)
        if len(unseen_article_urls) == 0:
            self.logger.info("--- Ingestion cycle finished. Seen all articles already. ---\n\n")
            return
        
        # Step 3: Filter out articles that haven't been seen
        unseen_urls_set: Set[str] = set(unseen_article_urls)
        unseen_articles: List[Article] = [article for article in unique_articles if article.link in unseen_urls_set]
        
        # Step 4: Publish unseen articles
        messages_to_publish: List[Any] = []
        for article in unseen_articles:
            payload = MessageURLPayload(url=article.link, source_rss=article.source)
            
            message = Message(
                header=MessageHeader(
                    message_id=hashlib.md5(article.link.encode()).hexdigest(),
                    timestamp=datetime.datetime.now().isoformat(),
                    type="background",
                ),
                data=payload,
            )
            message_as_dict = message.model_dump()
            messages_to_publish.append(message_as_dict)

        if len(messages_to_publish) == 0:
            self.logger.info(
                "--- Ingestion cycle finished. Cannot publish for some reason. ---\n\n"
            )
            return

        published_ids:List[str] = self.publisher.publish_many(messages_to_publish)
        number_of_published_ids: int = len(published_ids)
        if number_of_published_ids == 0:
            self.logger.info("--- Ingestion cycle finished. Could not publish to queue. ---\n\n")
            return

        # Step 5: Add urls to cache for future cycles
        self.duplicate_filter.add_many(unseen_article_urls)
        
        self.logger.info("--- Ingestion cycle finished ---")
        self.logger.info(f"\tNew: {len(unseen_articles)}")
        self.logger.info(f"\tSeen: {len(raw_articles) - len(unseen_articles)}")
        self.logger.info(f"\tTotal: {len(raw_articles)}")
        self.logger.info("-" * 10)
