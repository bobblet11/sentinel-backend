import redis
import os
import threading
from common.requests.retry_request import exponential_retry

REDIS_HOST = str(os.getenv("REDIS_HOST", "redis"))
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
    
class RedisConnection:
    """
    A thread-safe Singleton class to manage the Redis client connection.
    """
    
    _instance = None
    _lock = threading.Lock() 
    MAX_RETRIES = 5
    INITIAL_DELAY = 1 #s
  
  
    def __new__(cls):
        """
        before __init__, make sure no other class instance already exists with a connection pool. Enforces Singleton rule.
        """

        # Singleton instance already exists
        if cls._instance is not None:
            print("RedisConnectionPool already exists. Reusing instance...")
            return cls._instance
        
        
        # Singleton instance does not exist, attempt creation with lock.
        with cls._lock:
            if cls._instance is not None:
                print("RedisConnectionPool already exists. Reusing instance...")
                return cls._instance
            
            cls._instance = super(RedisConnection, cls).__new__(cls)
            cls._instance._client = None
            
            print("RedisConnection Singleton created.")
            return cls._instance


    @exponential_retry(max_attempts = MAX_RETRIES, initial_delay_s = INITIAL_DELAY)
    def connect(self):
        """
        Idempotently attempts to establish a connection to the Redis server.
        """ 
        
        print(f"Attempting to connect to Redis at {REDIS_HOST}:{REDIS_PORT}.")

        pool = redis.ConnectionPool(
            host=REDIS_HOST, 
            port=REDIS_PORT, 
            db=0, 
            decode_responses=True
        )

        client = redis.Redis(connection_pool=pool)

        if client.ping():
            print("Successfully pinged Redis.")
            self._client = client
            return True
        else:
            print("Failed to ping Redis.")
            raise redis.exceptions.ConnectionError("Redis ping returned False.")


    def get_client(self):
        """
        Returns the active Redis client. Connects if not already connected.
        """

        # Client already exists
        if self._client is not None:
            return self._client

        # Client does not exist, attempt to connect with lock.
        with self._lock:
           
            if self._client is not None:
                return self._client
                
            self.connect()
        
        return self._client


    def ping(self) -> bool:
        """
        Pings the Redis server to check the health of the connection.
        """
        if not self._client:
            print("No connection to ping. Connect first!")
            return False
        
        try:
            return self._client.ping()
        except redis.exceptions.ConnectionError:
            return False
       

    def close(self):
        """
        Closes the Redis connection pool.
        """
        if not self._client:
            print("No connection to close. Connect first!")
            
        print("Closing Redis connection...")
        self._client.connection_pool.disconnect()
        self._client = None

redis_connection = RedisConnection()