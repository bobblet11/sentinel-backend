
version = "0.0.1"

from .batches import Batch, batch_action, multithreaded_batch_action
from .retry_request import retry, exponential_retry

__all__ = [
    'Batch',
    'batch_action',
    'multithreaded_batch_action',
    'retry',
    'exponential_retry', 
]

print(f"Welcome to the Requests package version {version}.")