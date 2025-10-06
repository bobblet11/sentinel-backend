# common/redis_client/connection.py
import redis
import os
import threading
import time

"""
    These env variables are injected in the docker-compose.yml file.
"""
redis_host = os.getenv("REDIS_HOST", "redis")
redis_port = int(os.getenv("REDIS_PORT", 6379))

class RedisConnection:
    """
    A thread-safe Singleton class to manage the Redis client connection.

    This ensures that there is only one connection pool established per service,
    which is the most efficient way to interact with Redis.
    """
    
    # class instances
    _instance = None
    _lock = threading.Lock() 
    
    # Configuration for connection retries
    MAX_RETRIES = 5
    RETRY_DELAY_SECONDS = 3

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
        
        if self._client:
            return
        
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                print(f"Connecting to Redis at {redis_host}:{redis_port} (Attempt {attempt}/{self.MAX_RETRIES})...")
                
                pool = redis.ConnectionPool(
                    host=redis_host, 
                    port=redis_port, 
                    db=0, 
                    decode_responses=True
                )
                client = redis.Redis(connection_pool=pool)
                
                if client.ping():
                    print("Successfully connected and pinged Redis.")
                    self._client = client
                    return
                else:
                    raise redis.exceptions.ConnectionError("Redis ping returned False.")
            
            except redis.exceptions.ConnectionError as e:
                print(f"Connection attempt {attempt} failed: {e}")
                if attempt == self.MAX_RETRIES:
                    print("FATAL: Could not connect to Redis after all retries. Exiting.")
                    raise 
                print(f"Retrying in {self.RETRY_DELAY_SECONDS} seconds...\n")
                time.sleep(self.RETRY_DELAY_SECONDS)

    def get_client(self):
        """
        Returns the active Redis client. Connects if not already connected.
        This is the primary method other parts of the app should use.
        """
        # This check is not strictly necessary with the lock, but it's a fast path
        if self._client is None:
            # Use the lock to ensure connect() is only called by one thread
            with self._lock:
                # Double-check if another thread connected while we waited for the lock
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

redis_connection = RedisConnection()