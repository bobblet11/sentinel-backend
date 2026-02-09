import concurrent.futures

from dataclasses import dataclass
from feedparser import FeedParserDict, parse
from logging import Logger, getLogger
from typing import Dict, Iterator, List
from common.models.api.redis_models import Article
from common.redis_client.duplicate_filter import RedisDuplicateFilter
from common.redis_client.publisher import RedisPublisher
from common.requests.user_agent_manager import user_agent_manager
from .base_ingestor import BaseIngestor
from microservices.ingestor.config import MAX_INGESTOR_WORKERS, OUTPUT_STREAM, REDIS_DUPLICATE_FILTER_KEY

class RssIngestor(BaseIngestor):
    """
    An implementation of the BaseIngestor class tailored towards fetching
    and parsing multiple RSS feeds concurrently.
    """
    def __init__(self,feed_urls: List[str], duplicate_filter = None, publisher = None):
        """
        Initializes the ingestor with a list of RSS feed URLs.
        """

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
        
        super().__init__(duplicate_filter, publisher)
        if not isinstance(feed_urls, list) or not feed_urls:
            raise ValueError("feed_urls must be a non-empty list of strings.")
        self.feed_urls = feed_urls
        self.logger: Logger = getLogger("rss_ingestor")
        


    def _fetch_and_parse_feed(self, rss_url: str) -> FeedParserDict | None:
        """
        Fetches and parses a single RSS feed. Will be executed in multithreaded fashion.
        """
        try:
            feed:FeedParserDict = parse(rss_url, agent=user_agent_manager.generate_profile().user_agent_string)
            if feed.bozo:
                raise feed.bozo_exception
            return feed

        except Exception as e:
            self.logger.error(f"Failed to parse RSS feed {rss_url}. {e}")
            return None

    
    def fetch_articles(self, max_workers:int = MAX_INGESTOR_WORKERS) -> Iterator[Article]: 
        """
        Concurrently fetches all RSS feeds using a thread pool and yields
        article dictionaries in a standardized format.
        """

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_feed = executor.map(self._fetch_and_parse_feed, self.feed_urls)
            for feed in future_to_feed:
                if not feed:
                    continue

                self.logger.debug(f"\tProcessing entries from: {feed.feed.get('title', 'Unknown Title')}")

                for entry in feed.entries:

                    if not hasattr(entry, "link"):
                        continue
                    
                    yield Article(
                        link = entry.link,
                        source = feed.href,
                        title = entry.title,
                        summary = entry.summary if hasattr(entry, "summary") else None,
                    )


        # def _test_rss_feeds(self) -> Dict[str, int]:

    #     failed_feeds_count = 0
    #     successful_feeds_count = 0
    #     with concurrent.futures.ThreadPoolExecutor() as executor:
    #         future_to_feed = executor.map(self._fetch_and_parse_feed, self.feed_urls)
    #         for feed in future_to_feed:
    #             if not feed:
    #                 failed_feeds_count+=1
    #             successful_feeds_count+=1

    #     return {"success" : successful_feeds_count, "fail" : failed_feeds_count}
