from common.redis_client.publisher import RedisPublisher
from common.redis_client.duplicate_filter import RedisDuplicateFilter
from common.models.redis_models import Message, MessageHeader, MessageURLPayload
from common.requests.batches import Batch, multithreaded_batch_action
import datetime
import hashlib

class BaseIngestor:    
	"""
	A base class that defines the template for an ingestion workflow.

	Subclasses must implement the `_fetch_articles` generator method.
	"""
	
	def __init__(self):
		self.duplicate_filter = RedisDuplicateFilter("ingestor")
		self.publisher = RedisPublisher("ingested_articles")

	def fetch_articles(self):
		"""
		Generator that fetches URLs from the RSS list.

		This method MUST be a generator that yields dictionaries, where each
		dictionary represents a single fetched article and must contain at least
		a "link" and "source" key.

		Example: yield {"link": "http://a.com", "source": "rss.xml"}
		"""
  
		raise NotImplementedError("Please Implement this method")

  
	def run(self, batch_size: int = 100):
		"""
		Main cycle of ingestor service. Fetches, Filters, and Publishes articles from RSS list.
  
		Args:
			batch_size (int): The number of articles to process per batch.
		"""
  
		print(f"--- Starting new ingestion cycle for {self.__class__.__name__} ---")
  
		valid_articles = [article for article in self.fetch_articles() if article.get("link") and article.get("source")]
		filtered_articles = list(set(all_articles))
  
		if not filtered_articles or len(filtered_articles) == 0 :
			print("--- Ingestion cycle finished. No articles found. ---")
			return

		print(f"Fetched a total of {len(filtered_articles)} articles from sources.")
		article_links = [article.get("link") for article in filtered_articles]
		unique_article_links = self.duplicate_filter.has_many(article_links)
  
		if not unique_article_links or len(unique_article_links) == 0:
			print("--- Ingestion cycle finished. No articles found. ---")
			return

		print(f"Found {len(unique_article_links)} new articles out of {len(filtered_articles)}.")
  
		messages_to_publish = []
  
		for article in filtered_articles:
			link = article.get("link")
			src = article.get("source")

			if link not in set(unique_article_links):
				continue

			payload = MessageURLPayload(
				url=link,
				source_rss=source
			)

			message = Message(
				header=MessageHeader(
					message_id=hashlib.md5(link.encode()).hexdigest(),
					timestamp=datetime.datetime.now().isoformat()
				),
				data=payload
			)

			messages_to_publish.append(message.model_dump())
		
		if not messages_to_publish or len(messages_to_publish) == 0:
			print("--- Ingestion cycle finished. No articles found. ---")
			return

		published_ids = self.publisher.publish_many(messages_to_publish) 
  
		if not published_ids or len(published_ids) == 0:
			print("--- Ingestion cycle finished. Could not publish to queue. ---")
			return

		self.duplicate_filter.add_many(new_links)
		print(f"--- Ingestion cycle finished.\n\tNew: {len(messages_to_publish)}\n\tSeen: {len(filtered_articles) - len(messages_to_publish)}\n\tTotal: {len(filtered_articles)}---")
		



