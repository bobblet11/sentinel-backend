import logging
import sys

def setup_logging(level=logging.INFO, container_name:str=""):
    """
    Configures the root logger to send messages to stdout.
    """
    
    # 1. Get the root logger
    root_logger = logging.getLogger()
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
