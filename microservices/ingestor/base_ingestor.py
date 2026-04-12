from datetime import datetime
import hashlib
import logging

from common.models.api.dtos.job import JobStage, JobStatus, JobType
from common.models.api.redis_models import Article, Message, MessageHeader, MessagePayload, MessageTimestamp, add_timestamp_to_message
from common.redis_client.duplicate_filter import RedisDuplicateFilter
from common.redis_client.publisher import RedisPublisher
from common.io.json_updater import JsonHandler
from microservices.ingestor.config import OUTPUT_STREAM, REDIS_DUPLICATE_FILTER_KEY
from typing import Iterator, Dict, Set, List, Any, Optional
from datetime import datetime
import re

OUTLET_PATTERNS = {
    r"(bbc\.com|bbc\.co\.uk|www\.bbc\.com)": "BBC",
    r"(theguardian\.com|www\.theguardian\.com)": "The Guardian",
    r"(cbc\.ca|www\.cbc\.ca)": "CBC",
    r"(euronews\.com|www\.euronews\.com)": "Euronews",
    r"(abcnews\.go\.com|abcnews\.com)": "ABC",
    r"(cbsnews\.com|www\.cbsnews\.com)": "CBS",
    r"(nbcnews\.com|www\.nbcnews\.com)": "NBC",
    r"(npr\.org|www\.npr\.org)": "NPR",
    r"(foxnews\.com|www\.foxnews\.com)": "Fox News",
    r"(reuters\.com|www\.reuters\.com)": "Reuters",
    r"(apnews\.com|www\.apnews\.com)": "AP News",
    r"(aljazeera\.com|www\.aljazeera\.com)": "Al Jazeera",
}

def match_outlet_name(article_url: str) -> Optional[str]:
    for pattern, outlet in OUTLET_PATTERNS.items():
        if re.search(pattern, article_url):
            return outlet
    return None


class BaseIngestor:
    """
    A base class that defines the template for an ingestion workflow.
    Subclasses must implement the `_fetch_articles` generator method.
    """

    def __init__(self, duplicate_filter = None, publisher = None):
        # If no duplicate_filter was provided, create the default one NOW.
        if duplicate_filter is None:
            self.duplicate_filter = RedisDuplicateFilter(REDIS_DUPLICATE_FILTER_KEY, ttl_s=0)
        else:
            self.duplicate_filter = duplicate_filter

        # Do the exact same thing for the publisher.
        if publisher is None:
            self.publisher = RedisPublisher(OUTPUT_STREAM)
        else:
            self.publisher = publisher
            
        self.logger: logging.Logger = logging.getLogger("base_ingestor")
        self.stats_json_handler = JsonHandler(filename="stats.json")


    def _log_stats(self, newly_seen_articles:int =0, non_new_articles:int=0, total_deduplicated_articles_processed:int=0) -> None:
        file_data = self.stats_json_handler.read_json()

        # Step 1: Generate key for our json file
        today = datetime.now().date().isoformat()

        # Step 2: Either append or create to this date's cycle
        entry = file_data.setdefault(today, {
            "newly_added_urls": 0,
            "already_seen_urls": 0,
            "total_urls_processed": 0,
            "cycles" : 0
        })
        entry["newly_added_urls"] += newly_seen_articles
        entry["already_seen_urls"] += non_new_articles
        entry["total_urls_processed"] += total_deduplicated_articles_processed
        entry["cycles"] += 1
        
        
        # Step 3: Prune to last 30 days
        MAX_DAYS = 30
        dates = sorted(file_data.keys())
        if len(dates) > MAX_DAYS:
            for old_date in dates[:-MAX_DAYS]:
                del file_data[old_date]


        # Step 4: Persist
        file_data[today] = entry
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
                
        # Step 2: Get rid of any duplicates and malformed articles
        unique_articles: Set[Article] = set([a for a in raw_articles if a.link])
        if not unique_articles:
            self.logger.info("--- Ingestion cycle finished. All urls are malformed or all duplicates. ---\n\n")
            return
        

        # Step 3: Filter out articles that have been seen
        unseen_urls: Set[str] = set(self.duplicate_filter.has_many(list([a.link for a in unique_articles])))
        if not unseen_urls:
            self.logger.info("--- Ingestion cycle finished. Seen all articles already. ---\n\n")
            return
        unseen_articles: List[Article] = [article for article in unique_articles if article.link in unseen_urls]
            
        # Step 4: Publish unseen articles
        messages_to_publish: List[Any] = []
        for article in unseen_articles:
            matched_outlet = match_outlet_name(article.link or None)
            news_outlet = matched_outlet or article.source
            payload = MessagePayload(article_url=article.link, news_outlet=news_outlet, title=article.title, summary=article.summary)
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
            add_timestamp_to_message(message=message, stage_name=JobStage.INGESTED)
            messages_to_publish.append(message.model_dump())
        if len(messages_to_publish) == 0:
            self.logger.info("--- Ingestion cycle finished. No messages to publish. ---\n\n")
            return
        published_ids:List[str] = self.publisher.publish_many(messages_to_publish)


        # Step 5: Add unseen urls to cache for future cycles
        self.duplicate_filter.add_many(list(unseen_urls))
        

        # Step 6: Update ingestion statistics
        no_unseen_articles = len(unseen_articles)
        no_seen_articles = len(unique_articles) - len(unseen_articles)
        no_raw_articles_fetched = len(raw_articles)
        no_raw_deduplicated_articles_fetched = len(unique_articles)
        self._log_stats(no_unseen_articles, no_seen_articles, no_raw_deduplicated_articles_fetched)
        

        # Step 7: Log results
        self.logger.info("--- Ingestion cycle finished ---")
        self.logger.info(f"\tNew articles encountered: {no_unseen_articles}")
        self.logger.info(f"\tPreviously seen articles encountered: {no_seen_articles}")
        self.logger.info(f"\tTotal fetched: {no_raw_articles_fetched} (deduplicated count: {no_raw_deduplicated_articles_fetched})")
        self.logger.info(f"\tCachce size after: {self.duplicate_filter.client.scard(self.duplicate_filter.key_name)}")
        self.logger.info("-" * 10)
