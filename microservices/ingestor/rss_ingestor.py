import feedparser
import concurrent.futures
from typing import List, Dict, Iterator
from .base_ingestor import BaseIngestor

class RssIngestor(BaseIngestor):    
    """
    An implementation of the BaseIngestor class tailored towards fetching 
    and parsing multiple RSS feeds concurrently.
    """
    
    def __init__(self, feed_urls: List[str]):
        """
        Initializes the ingestor with a list of RSS feed URLs.

        Args:
            feed_urls List[str]: A list of URLS to RSS feeds to be processed.
            
        """
        super().__init__() 
        if not isinstance(feed_urls, list) or not feed_urls:
            raise ValueError("feed_urls must be a non-empty list of strings.")
        self.feed_urls = feed_urls
        
    
    def _fetch_and_parse_feed(self, url: str) -> feedparser.FeedParserDict | None:
        """
        Fetches and parses a single RSS feed. Will be executed in multithreaded fashion.

        Args:
            url (str): The URL of the RSS feed to fetch.

        Returns:
            A parsed feed object from feedparser
        """
        try:
            print(f"Fetching RSS feed: {url}")
            feed = feedparser.parse(url)
            
            if feed.bozo:
                raise feed.bozo_exception
            
            return feed
        
        except Exception as e:
            print(f"Error fetching or parsing feed {url}: {e}")
            return None
        
        
    def fetch_articles(self) -> Iterator[Dict[str, str]]:
        """
        Concurrently fetches all RSS feeds using a thread pool and yields
        article dictionaries in a standardized format.
        """
        
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future_to_feed = executor.map(self._fetch_and_parse_feed, self.feed_urls)
            for feed in future_to_feed:

                if not feed:
                    continue

                print(f"Processing entries from: {feed.feed.get('title', 'Unknown Title')}")
                
                
                for entry in feed.entries:
                
                    if not hasattr(entry, 'link'):
                        continue
                    
                    yield {
                        "link": entry.link,
                        "source": feed.href, 
                        "title": entry.title,
                        "summary": entry.summary if hasattr(entry, 'summary') else None
                    }