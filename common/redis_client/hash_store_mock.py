import json
import redis
from typing import Any, Dict, Optional, List
from logging import Logger, getLogger

from common.redis_client.connection import redis_connection


class RedisHashStoreMock:
    """
    A high-level Redis interface for managing collections of dictionaries
    stored as Redis hashes, keyed by a unique identifier.

    It allows creating, reading, updating, and deleting dictionary-like records
    in Redis with automatic serialization and deserialization to JSON.
    """

    def __init__(self, hash_namespace: str) -> None:
        """
        Initializes the RedisHashStore.

        Args:
            hash_namespace: The base Redis key under which all records are stored.
                For example, 'users' will store records like 'users:<uid>'.
        """

        if not isinstance(hash_namespace, str) or not hash_namespace:
            raise ValueError("hash_namespace must be a non-empty string.")

        self.hash_namespace: str = hash_namespace
        # self.client: redis.Redis = redis_connection.get_client()
        self.logger: Logger = getLogger(f"{hash_namespace}.redis_hash_store")

        self.logger.info(f"--- Initialized RedisHashStore for namespace: '{self.hash_namespace}' ---")

    def _key(self, uid: str) -> str:
        """
        Internal helper to compute the Redis key for a given UID.
        """
        return f"{self.hash_namespace}:{uid}"

    def set(self, uid: str, data: Dict[str, Any]) -> None:
        """
        Stores a dictionary under a unique UID key, overwriting any existing record.

        Args:
            uid: Unique identifier for the record.
            data: The dictionary to store.
        """
        if not isinstance(data, dict):
            raise ValueError("`data` must be a dictionary.")

        try:
            # Serialize all values to JSON for consistency.
            serialized_data = {k: json.dumps(v) for k, v in data.items()}
            # self.client.hset(self._key(uid), mapping=serialized_data)
            self.logger.info(f"Added to hash set {serialized_data}")
            self.logger.debug(f"Stored data for UID: {uid}")
        except Exception as e:
            self.logger.error(f"Failed to store data for UID '{uid}': {e}")
            raise e

    def get(self, uid: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves a dictionary by UID.

        Args:
            uid: Unique identifier of the record.

        Returns:
            The decoded dictionary if found, or None if missing.
        """
        try:
            self.logger.info(f"Getting all items")
            raw_data = {}
            if not raw_data:
                return None

            # Deserialize each field from JSON.
            self.logger.info(f"Deserialising result")
            decoded = {}
            return decoded

        except Exception as e:
            self.logger.error(f"Failed to get data for UID '{uid}': {e}")
            raise e

    def update(self, uid: str, updates: Dict[str, Any]) -> None:
        """
        Updates one or more fields of a record without overwriting the entire hash.

        Args:
            uid: Unique identifier of the record.
            updates: Dictionary of fields to update.
        """
        if not isinstance(updates, dict):
            raise ValueError("`updates` must be a dictionary.")

        try:
            serialized = {k: json.dumps(v) for k, v in updates.items()}
            # self.client.hset(self._key(uid), mapping=serialized)
            self.logger.debug(f"Updated fields for UID: {uid}")
        except Exception as e:
            self.logger.error(f"Failed to update data for UID '{uid}': {e}")
            raise e

    def delete(self, uid: str) -> None:
        """
        Deletes the entire record associated with the given UID.
        """
        try:
            self.logger.info(f"Deleting {uid}")
            result = 1
            # result = self.client.delete(self._key(uid))
            if result == 0:
                self.logger.warning(f"No record found for UID '{uid}' to delete.")
            else:
                self.logger.debug(f"Deleted record for UID '{uid}'.")
        except Exception as e:
            self.logger.error(f"Failed to delete UID '{uid}': {e}")
            raise e

    def exists(self, uid: str) -> bool:
        """
        Checks whether a record exists for the given UID.
        """
        try:
            self.logger.info(f"Checking if {uid} exist")
            result = 1
            return result
            # return self.client.exists(self._key(uid)) == 1
        except Exception as e:
            self.logger.error(f"Failed to check existence for UID '{uid}': {e}")
            raise e

    def list_all(self, pattern: Optional[str] = "*") -> List[str]:
        """
        Lists all record keys under this namespace (optionally filtered by pattern).
        """
        full_pattern = f"{self.hash_namespace}:{pattern}"
        self.logger.info(f"Checking pattern in hash set {full_pattern}")
        try:
            keys = []
            # keys = [key.decode() for key in self.client.keys(full_pattern)]
            return keys
        except Exception as e:
            self.logger.error(f"Failed to list keys: {e}")
            raise e
