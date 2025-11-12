import datetime
import hashlib

from common.models.api.redis_models import Message, MessageHeader, MessageURLPayload
from common.redis_client.duplicate_filter import RedisDuplicateFilter
from common.redis_client.publisher import RedisPublisher


class BaseIngestor:
    """
    A base class that defines the template for an ingestion workflow.

    Subclasses must implement the `_fetch_articles` generator method.
    """

    def __init__(self):
        self.duplicate_filter = RedisDuplicateFilter("ingestor:seen.articles")
        self.publisher = RedisPublisher("ingestor:to.be.scraped")

    def fetch_articles(self):
        """
        Generator that fetches URLs from the RSS list.

        This method MUST be a generator that yields dictionaries, where each
        dictionary represents a single fetched article and must contain at least
        a "link" and "source" key.

        Example: yield {"link": "http://a.com", "source": "rss.xml"}
        """

        raise NotImplementedError("Please Implement this method")

    def run(self):
        """
        Main cycle of ingestor service. Fetches, Filters, and Publishes articles from RSS list.
        """

        # Step 1: Fetch and filter articles from RSS
        print(f"--- Starting new ingestion cycle for {self.__class__.__name__} ---")
        unique_articles_map = {}
        for article in self.fetch_articles():
            link = article.get("link")
            if link and link not in unique_articles_map:
                unique_articles_map[link] = article
        if not unique_articles_map:
            print("--- Ingestion cycle finished. No articles found. ---\n\n")
            return
        total_fetched = len(unique_articles_map)
        # print(f"Fetched a total of {total_fetched} unique articles from sources.")

        # Step 2: Check if article has already been seen
        all_links = list(unique_articles_map.keys())
        unseen_article_links = self.duplicate_filter.has_many(all_links)
        if not unseen_article_links:
            print("--- Ingestion cycle finished. Seen all articles already. ---\n\n")
            return

        unseen = len(unseen_article_links)
        # print(f"Found {unseen} new articles out of {total_fetched}.")

        messages_to_publish = []
        for link in unseen_article_links:
            article = unique_articles_map[link]

            payload = MessageURLPayload(url=link, source_rss=article.get("source"))
            message = Message(
                header=MessageHeader(
                    message_id=hashlib.md5(link.encode()).hexdigest(),
                    timestamp=datetime.datetime.now().isoformat(),
                    type="background",
                ),
                data=payload,
            )

            messages_to_publish.append(message.model_dump())

        if not messages_to_publish:
            print(
                "--- Ingestion cycle finished. Cannot publish for some reason. ---\n\n"
            )
            return

        published_ids = self.publisher.publish_many(messages_to_publish)

        if not published_ids:
            print("--- Ingestion cycle finished. Could not publish to queue. ---\n\n")
            return

        self.duplicate_filter.add_many(unseen_article_links)
        print("--- Ingestion cycle finished ---")
        print(f"\tNew: {unseen}")
        print(f"\tSeen: {total_fetched - unseen}")
        print(f"\tTotal: {total_fetched}")
        print("-" * 10)
