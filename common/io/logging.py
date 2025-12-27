import logging
import sys

from typing import Callable

def setup_logging(level=logging.INFO, container_name:str=""):
    """
    Configures the root logger to send messages to stdout.
    """
    
    # 1. Get the root logger
    root_logger:logging.Logger = logging.getLogger()
    root_logger.setLevel(level)

    # 2. Create a handler (Output to Console/Docker logs)
    handler = logging.StreamHandler(sys.stdout)
    
    # 3. Create a Formatter
    # Standard format: Time | Level | Logger Name | Message
    log_format = f'%(asctime)s - %(levelname)s - [{container_name}.%(name)s] - %(message)s'
    formatter = logging.Formatter(log_format)
    
    # 4. Attach
    handler.setFormatter(formatter)
    
    # Prevent adding multiple handlers if function is called twice
    if not root_logger.handlers:
        root_logger.addHandler(handler)

def get_logger(func: Callable, args: tuple) -> logging.Logger:
    """
    Tries to grab 'self.logger' from the instance if this is a class method.
    Otherwise, returns a logger named after the function's module.
    """
    
    # Check if this is a method call (args[0] is usually 'self')
    if args and hasattr(args[0], 'logger') and isinstance(args[0].logger, logging.Logger):
        return args[0].logger
    
    # Fallback: create a logger based on the function's module name
    return logging.getLogger(func.__module__)
