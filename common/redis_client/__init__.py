# Define a variable called version
version = "0.0.1"

# Print a welcome message
print(f"Welcome to the Redis Client package version {version}. This package contains the following packages\nRedisQueue class: create queue objects to interact with queues stored in the Redis DB\nredis_connection: Singleton connection object that maintains a connection to the Redis DB")

from .consumer import RedisQueue
from .connection import redis_connection 

__all__ = [
    'RedisQueue',
    'redis_connection', 
]