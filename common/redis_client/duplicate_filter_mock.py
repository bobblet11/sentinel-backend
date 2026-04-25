
from logging import getLogger
from typing import List


class RedisDuplicateFilterMock:
    """
    A high-level, reliable wrapper for Redis set-based string caches.
    Uses a "rolling" TTL on the entire set to manage memory over time.
    """

    def __init__(self):
        self.logger = getLogger(f"MOCK.redis_duplicate_filter")
        self.duplicate_filter = set()

    def has_one(self, item: str) -> bool:
        """
        Checks if a single string item already exists in the filter set.
        """
        try:
            if not item or item == "":
                raise Exception("No argument provided for checking")
            return item in self.duplicate_filter
        except Exception as e:
            self.logger.error(f"Unexpectedly failed to check if item {item} exists in set! {e}")
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
            exists_results:List[bool] = [1 if item in self.duplicate_filter else 0 for item in items]
            unseen_items: List[str] = [
                item for item, exists in zip(items, exists_results) if not exists
            ]
            return unseen_items
        except Exception as e:
            self.logger.error(
                f"Failed to check if {len(items)} items exist in set! {e}"
            )
            raise e

    def add_one(self, item: str) -> None:
        """
        Attempts to atomically add a string to the set.
        """

        try:
            if not item:
                raise Exception("No item to add")

            self.duplicate_filter.add(item)
            
        except Exception as e:
            self.logger.error(f"Failed to add item {item} to set {e}")
            raise e

    def add_many(self, items: list[str]) -> None:
        """
        Attempts to atomically add multiple items to the filter set and resets the set's expiration in a single atomic transaction.
        """

        try:
            if not items:
                raise Exception("No items to add")

            self.duplicate_filter.update(items)
            
        except Exception as e:
            self.logger.error(
                f"Failed to add {len(items)} items to set! {e}"
            )
            raise e
