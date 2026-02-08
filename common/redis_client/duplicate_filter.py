import redis

from typing import List
from common.redis_client.connection import redis_connection
from logging import Logger, getLogger

class RedisDuplicateFilter:
    """
    A high-level, reliable wrapper for Redis set-based string caches.
    Uses a "rolling" TTL on the entire set to manage memory over time.
    """

    def __init__(self, key_name: str, ttl_s: int = 604800):
        """
        key_name (str): The name of the Redis set to upload and check.
        ttl_s (str): The time in seconds a value can live in redis set. Default is 1 week
        """

        
        if not isinstance(key_name, str) or not key_name:
            raise ValueError("key_name must be a non-empty string.")
        
        self.logger = getLogger(f"{key_name}.redis_duplicate_filter")
        self.logger.info("--- Initializing RedisDuplicateFilter ---")
        

        self.key_name:str = key_name
        self.ttl_s:str = ttl_s
        self.client: redis.Redis = redis_connection.get_client()

        self.logger.info(f"--- Initialized RedisDuplicateFilter at {key_name} ---")

    def has_one(self, item: str) -> bool:
        """
        Checks if a single string item already exists in the filter set.
        """
        try:
            if not item or item == "":
                raise Exception("No argument provided for checking")
            return self.client.sismember(self.key_name, item)
        except Exception as e:
            self.logger.error(f"Unexpectedly failed to check if item {item} exists in set {self.key_name}! {e}")
            raise e

    def has_many(self, items: list[str]) -> list[str]:
        """
        Filters a list of items, returning only those not in the set.

        This uses a Redis pipeline to perform a multi-SISMEMBER check in a
        single network round-trip.
        
        Returns a sub-list containing only the items that were NOT FOUND in the Redis set.
        """

        try:
            if not items:
                raise Exception("No items to check")

            # The result will be a list of booleans [1, 0, 1, ...]s
            exists_results:List[bool] = self.client.smismember(self.key_name, items)
            
            unseen_items: List[str] = [
                item for item, exists in zip(items, exists_results) if not exists
            ]
            return unseen_items
        except Exception as e:
            self.logger.error(
                f"Failed to check if {len(items)} items exist in set {self.key_name}! {e}"
            )
            raise e

    def add_one(self, item: str) -> None:
        """
        Attempts to atomically add a string to the set.
        """

        try:
            if not item:
                raise Exception("No item to add")

            pipe = self.client.pipeline()
            pipe.sadd(self.key_name, item)
            pipe.expire(self.key_name, self.ttl_s)
            pipe.execute()
            
        except Exception as e:
            self.logger.error(f"Failed to add item {item} to set {self.key_name}! {e}")
            raise e

    def add_many(self, items: list[str]) -> None:
        """
        Attempts to atomically add multiple items to the filter set and resets the set's expiration in a single atomic transaction.
        """

        try:
            if not items:
                raise Exception("No items to add")

            pipe = self.client.pipeline()
            pipe.sadd(self.key_name, *items)
            pipe.expire(self.key_name, self.ttl_s)
            pipe.execute()
            
        except Exception as e:
            self.logger.error(
                f"Failed to add {len(items)} items to set {self.key_name}! {e}"
            )
            raise e
