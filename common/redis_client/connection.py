import os
import threading
from typing import Any

import redis
from common.requests.retry_request import exponential_retry

REDIS_HOST:str = str(os.getenv("REDIS_HOST", "redis"))
REDIS_PORT:int = int(os.getenv("REDIS_PORT", 6379))
REDIS_SSL: bool = str(os.getenv("REDIS_SSL", "false")).strip().lower() in {"1", "true", "yes", "on"}
REDIS_SSL_CERT_REQS: str = str(os.getenv("REDIS_SSL_CERT_REQS", "required")).strip().lower()
REDIS_USERNAME: str | None = os.getenv("REDIS_USERNAME") or None
REDIS_PASSWORD: str | None = os.getenv("REDIS_PASSWORD") or None

print(f"REDIS_HOST: {REDIS_HOST}")
print(f"REDIS_PORT: {REDIS_PORT}")
print(f"REDIS_SSL: {REDIS_SSL}")
print(f"REDIS_SSL_CERT_REQS: {REDIS_SSL_CERT_REQS}")
print(f"REDIS_USERNAME: {REDIS_USERNAME}")

def _build_connection_kwargs() -> dict[str, Any]:
    """Build Redis connection kwargs from environment variables."""
    kwargs: dict[str, Any] = {
        "host": REDIS_HOST,
        "port": REDIS_PORT,
        "db": 0,
        "decode_responses": True,
        "socket_timeout": 500,
        "socket_connect_timeout": 500,
        "retry_on_timeout": True,
    }

    if REDIS_USERNAME:
        kwargs["username"] = REDIS_USERNAME
    if REDIS_PASSWORD:
        kwargs["password"] = REDIS_PASSWORD

    if REDIS_SSL:
        kwargs["connection_class"] = redis.SSLConnection
        kwargs["ssl_check_hostname"] = False
        if REDIS_SSL_CERT_REQS in {"none", "no", "false", "0"}:
            kwargs["ssl_cert_reqs"] = "none"
        elif REDIS_SSL_CERT_REQS in {"optional", "want"}:
            kwargs["ssl_cert_reqs"] = "optional"
        else:
            kwargs["ssl_cert_reqs"] = "required"
    # print(kwargs)
    return kwargs


class RedisConnection:
    """
    A thread-safe Singleton class to manage the Redis client connection.
    """

    _instance = None
    _lock = threading.Lock()
    MAX_RETRIES:int = 5
    INITIAL_DELAY_S:int = 1

    def __new__(cls) -> None:
        """
        before __init__, make sure no other class
        instance already exists with a connection pool. Enforces Singleton rule.
        """

        # Singleton instance already exists
        if cls._instance is not None:
            return cls._instance

        # Singleton instance does not exist, attempt creation with lock.
        with cls._lock:
            if cls._instance is not None:
                return cls._instance

            cls._instance:RedisConnection = super(RedisConnection, cls).__new__(cls)
            cls._instance._client= None

            return cls._instance

    @exponential_retry(
        max_attempts=MAX_RETRIES,
        initial_delay_s=INITIAL_DELAY_S,
        on_exceptions=(
            redis.exceptions.ConnectionError,
            redis.exceptions.TimeoutError,
            redis.exceptions.BusyLoadingError
        ),
    )
    def connect(self) -> bool:
        """
        Idempotently attempts to establish a connection to the Redis server.
        """
        pool = redis.ConnectionPool(**_build_connection_kwargs())

        client = redis.Redis(connection_pool=pool)

        if client.ping():
            self._client = client
            return True
        else:
            # raise error to let the retry mechanism catch it
            raise redis.exceptions.ConnectionError("Redis ping returned False.")


    def get_client(self) -> redis.Redis:
        """
        Returns the active Redis client. Connects if not already connected.
        """

        if self._client is not None:
            return self._client

        with self._lock:
            if self._client is not None:
                return self._client

            self.connect()
            
        try:
            self._client.ping()
        except redis.exceptions.ConnectionError:
            self.connect()
            
        return self._client

    def ping(self) -> bool:
        """
        Pings the Redis server to check the health of the connection.
        """
        if not self._client:
            return False

        try:
            return self._client.ping()
        except redis.exceptions.ConnectionError:
            return False

    def close(self) -> None:
        """
        Closes the Redis connection pool.
        """
        if not self._client:
            return

        self._client.connection_pool.disconnect()
        self._client = None

redis_connection:RedisConnection = RedisConnection()
