import logging
import sys

from typing import Callable

NOISY_LOGGERS = [
        "seleniumwire", 
        "hpack", 
        "urllib3", 
        "urllib3.connectionpool", 
        "websockets",
        "undetected_chromedriver",
        "requests",
        "web_scraper.selenium.webdriver.remote.remote_connection",
        "web_scraper.selenium.webdriver.common.service",
        "selenium",
        "selenium.webdriver.remote.remote_connection",
        "selenium.webdriver.common.service",
        "hpack",
        "urllib3",
        "websockets",
        "asyncio",
    ]

def setup_logging(level=logging.INFO, container_name:str=""):
    """
    Configures the root logger to send messages to stdout.
    """
    
    root_logger:logging.Logger = logging.getLogger()
    root_logger.setLevel(level)

    if not root_logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        
        # Standard format: Time | Level | Logger Name | Message
        log_format = f'%(asctime)s - %(levelname)s - [{container_name}.%(name)s] - %(message)s'
        formatter = logging.Formatter(log_format)
        
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)
    
    for logger_name in NOISY_LOGGERS:
        logging.getLogger(logger_name).setLevel(logging.WARNING)

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
