import functools
import time
from math import exp
from random import uniform


def retry(max_attempts=3, delay_s=1):
    def decorator_retry(func):
        def wrapper(*args, **kwargs):
            for attempt in range(1, max_attempts + 1):
                try:
                    print(f"Attempt #{attempt}")
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_attempts:
                        print(f"Fatal failure at attempt {attempt}. Exiting...")
                        raise e

                    print(
                        f"Failure at attempt {attempt}. Will retry in {delay_s:.2f} s"
                    )
                    time.sleep(delay_s)

        return wrapper

    return decorator_retry


def exponential_retry(
    max_attempts: int = 3,
    on_exceptions: tuple = (),
    initial_delay_s: float = 1,
    growth_modifier: float = 1,
    growth_rate: float = 1,
    jitter=False,
):
    def decorator_exponential_retry(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(1, max_attempts + 1):
                try:
                    print(f"Attempt #{attempt}")
                    return func(*args, **kwargs)

                # It now catches only the exceptions you specified. If exception not here, then it will raise
                except on_exceptions as e:
                    last_exception = e

                    # If you reach here, then all attempts failed.
                    if attempt == max_attempts:
                        print(f"Fatal failure at attempt {attempt}. Exiting...")
                        # Will raise an exception
                        break

                    time_to_wait_s = (
                        growth_modifier * exp(attempt * growth_rate)
                    ) + initial_delay_s

                    if jitter and time_to_wait_s > 1:
                        time_to_wait_s = uniform(time_to_wait_s - 1, time_to_wait_s + 1)

                    print(
                        f"[Retry] Attempt {attempt} failed for '{func.__name__}' with {type(e).__name__}. Retrying in {time_to_wait_s:.2f}s..."
                    )

                    time.sleep(time_to_wait_s)

            print(
                f"[Retry] All {max_attempts} attempts for '{func.__name__}' failed. Raising final error."
            )
            raise last_exception

        return wrapper

    return decorator_exponential_retry
