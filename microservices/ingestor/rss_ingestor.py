
import sys
import os
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
            feed_urls (List[str]): A list of URLs for the RSS feeds to be processed.
        """
        
        super().__init__() 
        if not isinstance(feed_urls, list) or not feed_urls:
            raise ValueError("feed_urls must be a non-empty list of strings.")
        
        self.feed_urls = feed_urls
    
    def _fetch_and_parse_feed(self, url: str) -> feedparser.FeedParserDict | None:
        """
        Fetches and parses a single RSS feed.
        Includes error handling to prevent one bad feed from stopping the process.

        Args:
            url (str): The URL of the RSS feed to fetch.

        Returns:
            A parsed feed object from feedparser, or None if an error occurs.
        """
        try:
            print(f"Fetching feed: {url}")
            feed = feedparser.parse(url)
            
            if feed.bozo:
                # bozo is set to 1 if the feed is not well-formed
                raise feed.bozo_exception
            return feed
        
        except Exception as e:
            print(f"Error fetching or parsing feed {url}: {e}")
            return None
        
        
    def fetch_articles(self) -> Iterator[Dict[str, str]]:
        
        """
        Implementation of the abstract method from BaseIngestor.

        Concurrently fetches all RSS feeds using a thread pool and yields
        article dictionaries in a standardized format.
        """
        
        # Use a ThreadPoolExecutor to fetch feeds in parallel.
        # This is ideal for I/O-bound tasks like waiting for network responses.
        
        with concurrent.futures.ThreadPoolExecutor() as executor:
            # map() applies the function to every item in self.feed_urls
            # and returns an iterator for the results.
            future_to_feed = executor.map(self._fetch_and_parse_feed, self.feed_urls)

            for feed in future_to_feed:
                # If a feed failed to fetch/parse, it will be None. Skip it.
                if not feed:
                    continue

                print(f"Processing entries from: {feed.feed.get('title', 'Unknown Title')}")
                
                # Process each entry in the successfully parsed feed
                for entry in feed.entries:
                    # Ensure the entry has a link, otherwise it's not useful
                    if not hasattr(entry, 'link'):
                        continue

                    # Yield article data in the format expected by BaseIngestor
                    yield {
                        "link": entry.link,
                        "source": feed.href, # The original URL of the feed
                        "title": entry.title,
                        "summary": entry.summary if hasattr(entry, 'summary') else ""
                    }