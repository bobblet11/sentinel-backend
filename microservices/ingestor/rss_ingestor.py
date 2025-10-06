import sys
import os
sys.path.append('/workspaces/Sentinel')

from base_ingestor import BaseIngestor
import feedparser

class RssIngestor(BaseIngestor):    
    """
    An implementation of the BaseIngestor class tailored towards fetching from RSS feeds
    """
    
    def __init__(self, feeds_path: str):
        super().__init__()  # Important: call parent constructor
        self.feeds_path = feeds_path
    
    def fetch_articles(self):
        """
        Implementation of the abstract method from BaseIngestor.
        This should be a generator that yields article dictionaries.
        """
        # For testing, let's use a sample RSS feed
        rss_url = "https://www.nasa.gov/rss/dyn/breaking_news.rss"
        feed = feedparser.parse(rss_url)

        print(f"Feed Title: {feed.feed.title}")
        print(f"Feed Link: {feed.feed.link}\n")

        for entry in feed.entries:
            print(f"Entry Title: {entry.title}")
            print(f"Entry Link: {entry.link}")
            if hasattr(entry, 'summary'):
                print(f"Entry Summary: {entry.summary}")
            print("-" * 20)
            
            # Yield article data in the format expected by BaseIngestor
            yield {
                "link": entry.link,
                "source": rss_url,
                "title": entry.title,
                "summary": entry.summary if hasattr(entry, 'summary') else ""
            }

# Test the RSS ingestor
if __name__ == "__main__":
    # Create an instance and test it
    ingestor = RssIngestor("path/to/feeds.json")  # You can pass a dummy path for testing
    
    # Test fetching articles
    print("=== Testing RSS Ingestion ===")
    articles = list(ingestor.fetch_articles())
    print(f"Fetched {len(articles)} articles")
    
    # Test the full ingestion cycle
    print("\n=== Testing Full Ingestion Cycle ===")
    ingestor.run()