
from .rss_ingestor import RssIngestor

if __name__ == "__main__":
	rss_feeds = ["https://www.nasa.gov/rss/dyn/breaking_news.rss"]
	rss_ingestor = RssIngestor(rss_feeds) 
	rss_ingestor.run()