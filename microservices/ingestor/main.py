import json
import os
from microservices.ingestor.rss_ingestor import RssIngestor

if __name__ == "__main__":
        script_dir = os.path.dirname(os.path.abspath(__file__))
        json_file_path = os.path.join(script_dir, 'rss_feeds.json')
                
        with open(json_file_path, 'r') as file:
                rss_feeds = json.load(file)
        rss_ingestor = RssIngestor(rss_feeds) 
        rss_ingestor.run()
