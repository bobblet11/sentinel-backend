from common.redis_client.publisher import RedisPublisher
from common.redis_client.duplicate_filter import RedisDuplicateFilter
from common.models.redis_models import Message, MessageHeader, MessageURLPayload
import datetime
import hashlib

class BaseIngestor:    
	"""
	A base class that defines the template for an ingestion workflow.

	It handles the core, unchanging algorithm: fetching articles, checking for
	duplicates against Redis, and publishing new articles to a stream.

	Subclasses must implement the `_fetch_articles` generator method.
	"""
	
	def __init__(self):
		"""
			Initializes the Redis publisher and the Redis cache for duplicate checking.
		"""
		self.duplicate_filter = RedisDuplicateFilter("ingestor")
		self.publisher = RedisPublisher("ingested_articles")

	def fetch_articles(self):
		"""
  
		Abstract method to be implemented by subclasses.

		This method MUST be a generator that yields dictionaries, where each
		dictionary represents a single fetched article and must contain at least
		a "link" and "source" key.

		Example: yield {"link": "http://a.com", "source": "rss.xml"}
  
		"""
		raise NotImplementedError("Please Implement this method")

	def run(self, batch_size: int = 100):
		"""
		The main public template method that executes the entire ingestion cycle.
  
		Args:
			batch_size (int): The number of articles to process per batch.
		"""
  
		print(f"--- Starting new ingestion cycle for {self.__class__.__name__} ---")
  
		total_new = 0
		total_processed = 0
  
		try:
			all_articles = list(self.fetch_articles())
		except Exception as e:
			print(f"Failed to fetch articles: {e}")
			return

		if not all_articles:
			print("--- Ingestion cycle finished. No articles found. ---")
			return

		print(f"Fetched a total of {len(all_articles)} articles from sources.")
  
		for i in range(0, len(all_articles), batch_size):
			batch = all_articles[i:i + batch_size]
			total_processed += len(batch)

			batch_links = [article.get("link") for article in batch if article.get("link")]
			if not batch_links:
				continue

			try:
				# 1. Efficiently find which links are new.
    
				new_links=self.duplicate_filter.has_many(batch_links)
				if not new_links:
					print(f"Processed batch {i//batch_size + 1}: All {len(batch)} articles already seen.")
					continue
				print(f"Processed batch {i//batch_size + 1}: Found {len(new_links)} new articles out of {len(batch)}.")


				# 2. Prepare all the new messages for publishing.
				new_links_set = set(new_links)
				messages_to_publish = []
				for article in batch:
					if article.get("link") in new_links_set:
						article_link = article.get("link")
	
						payload = MessageURLPayload(
							url=article_link,
							source_rss=article.get("source", "unknown")
						)
	
						message = Message(
							header=MessageHeader(
								message_id=hashlib.md5(article_link.encode()).hexdigest(),
								timestamp=datetime.datetime.now().isoformat()
							),
							data=payload
						)
	
						messages_to_publish.append(message.model_dump())
      
				# 3. Atomically publish the batch and mark them as seen.
				if messages_to_publish:
					published_ids = self.publisher.publish_many(messages_to_publish) 
					
					# no need to deal with partial failure. THe entire batch will fail if even a single redis command fails, this is because its an atomic transaction
					if published_ids:
						self.duplicate_filter.add_many(new_links)
						total_new += len(published_ids)
					else:
						print("Failed to publish a batch of new articles. These will be retried next cycle.")
			except Exception as e:
				print(f"Failed to process a batch due to a Redis error: {e}. Skipping batch.")
	
		print(f"--- Ingestion cycle finished. New: {total_new}, Seen: {total_processed} ---")
		



