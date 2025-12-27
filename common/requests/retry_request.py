import functools
import time
from math import exp
from random import uniform
from typing import Callable, Any
from common.io.logging import get_logger
from logging import getLogger, Logger

def retry(max_attempts:int=3, delay_s:int=1) -> Callable:
    def decorator_retry(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            logger:Logger = get_logger(func, args)
            
            for attempt in range(1, max_attempts + 1):
                try:
                    logger.debug(f"Attempt #{attempt}")
                    return func(*args, **kwargs)
                
                except Exception as e:
                    if attempt == max_attempts:
                        logger.warning(f"Attempted all {max_attempts} attempts. Exiting...")
                        raise e
                    logger.warning(f"[Retry] Failure at attempt {attempt} doing '{func.__name__}' with error {type(e).__name__}. Will retry in {delay_s:.2f} s")
                    time.sleep(delay_s)
        return wrapper

    return decorator_retry


def exponential_retry(
    max_attempts: int = 3,
    on_exceptions: tuple = (),
    initial_delay_s: float = 1,
    growth_modifier: float = 1,
    growth_rate: float = 1,
    jitter:bool=False,
) -> Callable:
    def decorator_exponential_retry(func:Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            logger:Logger = get_logger(func, args)
            last_exception:Exception = None
            
            for attempt in range(1, max_attempts + 1):
                try:
                    logger.debug(f"Attempt #{attempt}")
                    return func(*args, **kwargs)

                except on_exceptions as e:
                    last_exception = e

                    # If you reach here, then all attempts failed.
                    if attempt == max_attempts:
                        logger.warning(f"Attempted all {max_attempts} attempts. Exiting...")
                        break

                    time_to_wait_s: float = (
                        growth_modifier * exp(attempt * growth_rate)
                    ) + initial_delay_s

                    if jitter and time_to_wait_s > 1:
                        time_to_wait_s = uniform(time_to_wait_s - 1, time_to_wait_s + 1)
                        
                    logger.warning(f"[Retry] Failure at attempt {attempt} doing '{func.__name__}' with error {type(e).__name__}. Will retry in {time_to_wait_s:.2f} s")
                    time.sleep(time_to_wait_s)
            raise last_exception
        return wrapper

    return decorator_exponential_retry
