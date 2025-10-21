from common.redis_client.connection import redis_connection

class RedisDuplicateFilter:    
	"""
	A high-level, reliable wrapper for Redis set-based string caches.
 	Uses a "rolling" TTL on the entire set to manage memory over time.

	Attributes:
 		key_name (str): The name of the Redis set used as the cache.
   		ttl_seconds (int): The TTL set for cache items.
		client: The connected redis-py client instance, managed by the RedisConnection singleton.
	"""
	
	def __init__(self, key_name: str, ttl_seconds:int = 604800):
		"""
		key_name (str): The name of the Redis set to upload and check.
		ttl_seconds (str): The time in seconds a value can live in redis set. Default is 1 week
		"""
  
		if not isinstance(key_name, str) or not key_name:
			raise ValueError("Set name must be a non-empty string.")

		self.key_name = key_name
		self.ttl_seconds = ttl_seconds
		self.client = redis_connection.get_client()
		
		print(f"Redis Duplicate Filter initialised for redis set {key_name}")
	
 
	def has_one(self, item:str) -> int:
		"""
		Checks if a single string item already exists in the filter set.
		"""

		try:
		
			if item not item or item == "":
				print("no item to check")
				raise Exception("no item to check")
          
          
			return self.client.sismember(self.key_name, item)
		except Exception as e:
			print(f"Redis Duplication Filter unexpectedly failed to check if item {item} exists in set {self.key_name}! {e}")
			raise
	
 
	def has_many(self, items: list[str]) -> list[str]:
		"""
		Filters a list of items, returning only those not in the set.

		This uses a Redis pipeline to perform a multi-SISMEMBER check in a 
		single network round-trip.

		Args:
			items (list[str]): A list of strings to check.

		Returns:
			list[str]: A sub-list containing only the items that were NOT FOUND in the Redis set.
		"""
  
		try:
			if not items or len(items) == 0:
				print("no items to check")
				raise Exception("No items to check")

			# The result will be a list of booleans [1, 0, 1, ...]
			exists_results = self.client.smismember(self.key_name, items)
			new_items = [item for item, exists in zip(items, exists_results) if not exists]
			return new_items
		except Exception as e:
			print(f"Redis Duplication Filter unexpectedly failed to check if {len(items)} items exists in set {self.key_name}! {e}")
			raise


	def add_one(self, item: str):
		"""
		Attempts to atomically add a string to the set.
		"""
	
		try:
			if not item or item == "":
				print("No item to add")
				raise Exception("No item to add")

			pipe = self.client.pipeline()
			pipe.sadd(self.key_name, item)
			pipe.expire(self.key_name, self.ttl_seconds)
			pipe.execute()
		except Exception as e:
			print(f"Redis Duplication Filter unexpectedly failed to add item {item} to set {self.key_name}! {e}")
			raise


	def add_many(self, items: list[str]):
		"""
		Attempts to atomically add multiple items to the filter set and resets the set's expiration in a single atomic transaction.
		"""
  
		try:
			if not items or len(items) == 0:
				print("No items to add")
				raise Exception("No items to add")
		
			pipe = self.client.pipeline()
			pipe.sadd(self.key_name, *items)
			pipe.expire(self.key_name, self.ttl_seconds)
			pipe.execute()
		except Exception as e:
			print(f"Redis Duplication Filter unexpectedly failed to add {len(items)} items to set {self.key_name}! {e}")
			raise