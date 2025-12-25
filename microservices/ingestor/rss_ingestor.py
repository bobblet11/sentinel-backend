import concurrent.futures

from dataclasses import dataclass
from feedparser import FeedParserDict, parse
from logging import Logger, getLogger
from typing import Dict, Iterator, List
from common.requests.user_agent_manager import user_agent_manager
from .base_ingestor import BaseIngestor
from microservices.ingestor.config import MAX_INGESTOR_WORKERS
@dataclass(frozen=True)
class Article:
    link: str
    summary: str
    title: str
    source: str = "Unknown Source"
    
class RssIngestor(BaseIngestor):
    """
    An implementation of the BaseIngestor class tailored towards fetching
    and parsing multiple RSS feeds concurrently.
    """

    def __init__(self, feed_urls: List[str]):
        """
        Initializes the ingestor with a list of RSS feed URLs.
        """
        super().__init__()
        if not isinstance(feed_urls, list) or not feed_urls:
            raise ValueError("feed_urls must be a non-empty list of strings.")
        
        self.logger: Logger = getLogger("rss_ingestor")
        self.feed_urls = feed_urls


    def _fetch_and_parse_feed(self, rss_url: str) -> FeedParserDict | None:
        """
        Fetches and parses a single RSS feed. Will be executed in multithreaded fashion.
        """
        try:
            feed:FeedParserDict = parse(rss_url, agent=user_agent_manager.get_random_agent())
            if feed.bozo:
                raise feed.bozo_exception
            return feed

        except Exception as e:
            self.logger.error(f"Failed to parse RSS feed {rss_url}. {e}")
            return None


    def fetch_articles(self) -> Iterator[Article]: 
        """
        Concurrently fetches all RSS feeds using a thread pool and yields
        article dictionaries in a standardized format.
        """

        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_INGESTOR_WORKERS) as executor:
            future_to_feed = executor.map(self._fetch_and_parse_feed, self.feed_urls)
            for feed in future_to_feed:
                if not feed:
                    continue

                self.logger.info(f"\tProcessing entries from: {feed.feed.get('title', 'Unknown Title')}")

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
