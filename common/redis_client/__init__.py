
version = "0.0.2"

from .consumer import RedisConsumer
from .publisher import RedisPublisher
from .duplicate_filter import RedisDuplicateFilter
from .object_cache import RedisObjectCache
from .connection import redis_connection 

__all__ = [
    'RedisConsumer',
    'RedisPublisher',
    'RedisDuplicateFilter',
    'RedisObjectCache',
    'redis_connection', 
]

print(f"Welcome to the Redis Client package version {version}.")