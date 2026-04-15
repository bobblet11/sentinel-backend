from datetime import datetime
import hashlib
import logging

from psycopg2 import OperationalError
from sqlalchemy import text



from common.models.api.dtos.job import JobStage, JobStatus, JobType
from common.models.api.redis_models import Article, Message, MessageHeader, MessagePayload, MessageTimestamp, add_timestamp_to_message
from common.models.api.validation_helpers import get_pretty_print_message, validate_after_ingestor
from common.redis_client.duplicate_filter import RedisDuplicateFilter
from common.redis_client.publisher import RedisPublisher
from common.io.json_updater import JsonHandler
from microservices.ingestor.config import OUTPUT_STREAM, REDIS_DUPLICATE_FILTER_KEY
from typing import Iterator, Dict, Set, List, Any, Optional, Tuple
from datetime import datetime
import re

from microservices.ingestor.db import get_db

OUTLET_PATTERNS = {
    r"(bbc\.com|bbc\.co\.uk|www\.bbc\.com)": "BBC",
    r"(theguardian\.com|www\.theguardian\.com)": "The Guardian",
    r"(cbc\.ca|www\.cbc\.ca)": "CBC",
    r"(euronews\.com|www\.euronews\.com)": "Euronews",
    r"(abcnews\.go\.com|abcnews\.com)": "ABC",
    r"(cbsnews\.com|www\.cbsnews\.com)": "CBS",
    r"(nbcnews\.com|www\.nbcnews\.com|feeds\.nbcnews\.com)": "NBC",
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
        self.db_snapshot_json_handler = JsonHandler(filename="db_snapshots.json")

    def _take_redis_snapshot(self) -> Tuple[int]:
        num_keys = self.publisher.client.dbsize()
        memory_info = self.publisher.client.info("memory")
        memory_used_bytes = memory_info.get("used_memory", 0)
        memory_used_human = memory_info.get("used_memory_human", "0B")

        return num_keys, memory_used_bytes, memory_used_human

    def _take_postgres_snapshot(self) -> int:
        """Return the size of the current Postgres database in bytes."""
        try:
            db = next(get_db())  # grab a session from your generator
            result = db.execute(text("SELECT pg_database_size(current_database())"))
            return result.scalar() or 0
        except OperationalError as e:
            logging.error(f"Failed to get Postgres size: {e}")
            return 0
        finally:
            db.close()
        
        
    
    def _log_snapshot(self) -> None:
        file_data = self.db_snapshot_json_handler.read_json()
        cycle_key = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        entry = file_data.setdefault(cycle_key, {
            "snapshots": []
        })

        num_keys, memory_used_bytes, memory_used_human = self._take_redis_snapshot()
        postgres_size = self._take_postgres_snapshot()
        
        snapshot = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "redis_keys": num_keys,
            "redis_memory_used": memory_used_bytes,
            "redis_memory_used_readable" : memory_used_human,
            "postgres_size": postgres_size
        }

        entry["snapshots"].append(snapshot)

        # Prune to last 30 days
        MAX_DAYS = 30
        dates = sorted(file_data.keys())
        if len(dates) > MAX_DAYS*24:
            for old_date in dates[:-MAX_DAYS]:
                del file_data[old_date]

        self.db_snapshot_json_handler.write_json(file_data)

    def _log_stats(self, newly_seen_articles:int =0, non_new_articles:int=0, total_deduplicated_articles_processed:int=0, total_raw_articles_fetched:int=0, outlet_counts:Dict[str, Any] = {}, cycle_duration_s:int = 0 ) -> None:
        file_data = self.stats_json_handler.read_json()

        # Step 1: Generate key for our json file
        cycle_key = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        # Step 2: Either append or create to this date's cycle
        entry = {
            "raw_total" : total_raw_articles_fetched,
            "deduplicated_total": total_deduplicated_articles_processed,
            "unseen": newly_seen_articles,
            "seen_skipped": non_new_articles,
            "outlet_counts": outlet_counts or {},
            "cycle_duration_s" : cycle_duration_s
        }
        
        file_data[cycle_key] = entry
                    
        # Step 3: Prune to last 30 days
        MAX_DAYS = 30
        dates = sorted(file_data.keys())
        if len(dates) > MAX_DAYS*24:
            for old_date in dates[:-MAX_DAYS]:
                del file_data[old_date]


        # Step 4: Persist
        file_data[cycle_key] = entry
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
        self._log_snapshot()
        
        start_time = datetime.now()
        # Step 1: Fetch articles from source
        raw_articles: List[Article] = list(self.fetch_articles())
        total_articles_ingested = len(raw_articles)
        if total_articles_ingested == 0:
            self.logger.info("Ingestion cycle: no articles found.")
            return

        # Step 2: Get rid of any duplicates and malformed articles
        unique_articles: Set[Article] = set([a for a in raw_articles if a.link])
        if not unique_articles:
            self.logger.info("Ingestion cycle: all URLs malformed or duplicate.")
            return
        
        # -- Report collection code --
        outlet_counts:Dict = {}
        for article in unique_articles:
            matched_outlet = match_outlet_name(article.link or None)
            news_outlet = matched_outlet or article.source
            if news_outlet and news_outlet.startswith("http"):
                news_outlet = "UNKNOWN"
                
            if news_outlet not in outlet_counts:
                outlet_counts[news_outlet] = {"total":1, "unseen":0, "seen_skipped": 0}
            else:
                outlet_counts[news_outlet]["total"] += 1
        # ----------------------------
            
        # Step 3: Filter out articles that have been seen
        unseen_urls: Set[str] = set(self.duplicate_filter.has_many(list([a.link for a in unique_articles])))
        if not unseen_urls:
            self.logger.info("Ingestion cycle: all articles already seen.")
            return
        unseen_articles: List[Article] = [article for article in unique_articles if article.link in unseen_urls]
            
        # Step 4: Publish unseen articles
        
        messages_to_publish: List[Any] = []
        for article in unseen_articles:
            
            matched_outlet = match_outlet_name(article.link or None)
            news_outlet = matched_outlet or article.source
            if news_outlet and news_outlet.startswith("http"):
                news_outlet = "UNKNOWN"
            
            outlet_counts[news_outlet]["unseen"] += 1
             
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
            
            validate_after_ingestor(message=message)
            self.logger.debug(get_pretty_print_message(message))
            
            messages_to_publish.append(message.model_dump())
            
        if len(messages_to_publish) == 0:
            self.logger.info("Ingestion cycle: no messages to publish.")
            return
        published_ids:List[str] = self.publisher.publish_many(messages_to_publish)

        # Step 5: Add unseen urls to cache for future cycles
        self.duplicate_filter.add_many(list(unseen_urls))
        
        # Step 6: Update ingestion statistics
        no_unseen_articles = len(unseen_articles)
        no_seen_articles = len(unique_articles) - len(unseen_articles)
        no_raw_articles_fetched = len(raw_articles)
        no_raw_deduplicated_articles_fetched = len(unique_articles)
        
        for outlet, stats in outlet_counts.items():
            stats["seen_skipped"] = stats["total"] - stats["unseen"]
        duration = (datetime.now() - start_time).total_seconds()
        self._log_stats(no_unseen_articles, 
                        no_seen_articles, 
                        no_raw_deduplicated_articles_fetched, 
                        total_articles_ingested, 
                        outlet_counts, 
                        duration)
        
        # Step 7: Log results
        self.logger.info(
            "Ingestion cycle done: new=%d seen=%d total_fetched=%d",
            no_unseen_articles,
            no_seen_articles,
            no_raw_articles_fetched,
        )
        
        
