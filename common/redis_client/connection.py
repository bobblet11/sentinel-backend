# common/redis_client/connection.py
import redis
import os
import threading

"""
    These env variables are injected in the docker-compose.yml file.
"""
redis_host = os.getenv("REDIS_HOST", "redis")
redis_port = os.getenv("REDIS_PORT", 6379)


class RedisConnection:
    """
    A thread-safe Singleton class to manage the Redis client connection.

    This ensures that there is only one connection pool established per service,
    which is the most efficient way to interact with Redis.
    """
    
    # class instances
    _instance = None
    _lock = threading.Lock() 

    def __new__(cls):
        """
        The __new__ method is the key to the Singleton pattern. It controls
        the object creation process itself.
        
        __new__ is called before __init__. It allocates a blank object 
        in memory
        """
        if cls._instance is None:
            # Use a lock to prevent race conditions in multi-threaded environments
            # (like a Gunicorn server) where two threads might try to create the instance at the exact same time.
            
            with cls._lock:
                
                # Double-check if another thread created the instance while we were waiting for the lock
                
                if cls._instance is None:
                    cls._instance = super(RedisConnection, cls).__new__(cls)
                    cls._instance._client = None
                    print("RedisConnection Singleton created.")
        return cls._instance

    def connect(self):
        """
        Establishes the connection to the Redis server.
        This method is idempotent; it will only connect if not already connected.
        """
        # _client is a class instance from the RedisConnection object
        if self._client is None:
            try:
                print(f"Attempting to connect to Redis at {redis_host}...")
                
                pool = redis.ConnectionPool(
                    host=redis_host, 
                    port=redis_port, 
                    db=0, 
                    decode_responses=True
                )
                self._client = redis.Redis(connection_pool=pool)
                self.ping()
                print("Successfully connected to Redis.")
                
            except redis.exceptions.ConnectionError as e:
                print(f"FATAL: Could not connect to Redis: {e}")
                self._client = None
                raise

    def get_client(self):
        """
        Returns the active Redis client. Connects if not already connected.
        This provides a "lazy connection" behavior.
        """
        if self._client is None:
            self.connect()
        return self._client

    def ping(self) -> bool:
        """
        Pings the Redis server to check the health of the connection.

        Returns:
            True if the connection is alive, False otherwise.
        """
        
        if self._client:
            try:
                return self._client.ping()
            except redis.exceptions.ConnectionError:
                return False
        return False

    def close(self):
        """
        Closes the Redis connection pool.
        Useful for graceful shutdowns or in tests.
        """
        if self._client:
            print("Closing Redis connection...")
            self._client.connection_pool.disconnect()
            self._client = None
            # We don't destroy the singleton instance, just the connection
            RedisConnection._instance = None 

# Create a single, globally accessible singleton instance of the connection manager
redis_connection = RedisConnection()