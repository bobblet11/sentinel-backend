import json
from microservices.ingestor.rss_ingestor import RssIngestor

if __name__ == "__main__":
        with open('./rss_feeds.json', 'r') as file:
                rss_feeds = json.load(file)
        rss_ingestor = RssIngestor(rss_feeds) 
        rss_ingestor.run()