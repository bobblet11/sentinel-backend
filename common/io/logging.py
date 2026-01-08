import logging
import sys
import os
import datetime
from pathlib import Path
from logging.handlers import TimedRotatingFileHandler
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


def setup_logging(level=logging.INFO, container_name:str="unknown_service", log_directory:Path=Path("/app/logs")):
    """
    Configures the root logger to send messages to stdout.
    """
    
    root_logger:logging.Logger = logging.getLogger()
    root_logger.setLevel(level)
    log_filename:str = f"service.log"
    
    if isinstance(log_directory, str):
        log_directory = Path(log_directory)
    
    log_directory.mkdir(mode=777,parents=True, exist_ok=True)
    log_filepath:Path = log_directory / log_filename
    log_filepath.touch(mode=777, exist_ok=True)
    os.chmod(str(log_filepath), 0o666)
    print(f"{log_filepath}")
    
    
    for logger_name in NOISY_LOGGERS:
        logging.getLogger(logger_name).setLevel(logging.WARNING)


    if root_logger.handlers:
        return
    
    # Standard format: Time | Level | Logger Name | Message
    log_format = f'%(asctime)s - %(levelname)s - [{container_name}.%(name)s] - %(message)s'
    formatter = logging.Formatter(log_format)
    
    stream_handler = logging.StreamHandler(sys.stdout)
    file_handler = TimedRotatingFileHandler(str(log_filepath), when='D', interval=1, backupCount=5, utc=True)
    handlers = [stream_handler, file_handler]
    
    for handler in handlers:
        handler.setFormatter(formatter)
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
