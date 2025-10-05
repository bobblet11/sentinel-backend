from .base_ingestor import BaseIngestor

class RssIngestor(BaseIngestor):    
	"""
	A implemntation of the BaseIngestor class tailored towards fetching from RSS feeds
 
	Given a structured JSON file containing RSS feed urls, the ingestor will periodically fetch and extract all articles from each RSS URL.
	
	RSS Ingestor will then check each artice to see if it has already been seen via a operation on a Redis Set 

	If article is not found in set, upload it to the Redis set.
	If article has been seen, ignore it.
 
	Attributes:
		feeds_path (str): The absolute path of the feed JSON file
	"""
	
	def __init__(self, feeds_path: str):
		pass
	
 
	def fetch_new_articles(self):
		"""
		fetches the current article list from each RSS feed in the RSS feed list.
		"""
		pass





	
