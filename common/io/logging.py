from dataclasses import asdict, dataclass
import logging
import sys
import os
import glob
import datetime
from pathlib import Path
from logging.handlers import TimedRotatingFileHandler
from typing import Any, Callable, List

NOISY_LOGGERS = [
        "seleniumwire", 
        "hpack", 
        "urllib3", 
        "urllib3.connectionpool", 
    "httpx",
    "httpcore",
    "filelock",
    "huggingface_hub",
    "transformers",
    "sentence_transformers",
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
@dataclass()
class TimeDeltaConfig:
    weeks: float = 0
    days: float = 1
    hours: float = 0
    minutes: float = 0
    
    @property
    def total_days(self):
        return (self.weeks * 7) + self.days + (self.hours / 24) + (self.minutes / 1440)


def _cleanup_old_logs(log_directory: Path, max_age_of_log_file: TimeDeltaConfig):
    """
    Finds and deletes log files older than the retention period.
    This acts as our manual logrotate.
    """
    if not log_directory.exists():
        return

    log_files: List[str] = glob.glob(str(log_directory / "cron-service-*.log"))
    cutoff_datetime = datetime.datetime.utcnow() - datetime.timedelta(**asdict(max_age_of_log_file))
    
    files_to_delete:List[Path] = []
    for log_file_path in log_files:
        try:
            file_date_str = Path(log_file_path).stem.replace('cron-service-', '')
            file_datetime = datetime.datetime.strptime(file_date_str, '%Y-%m-%d-%H-%M')
            
            if file_datetime < cutoff_datetime:
                files_to_delete.append(log_file_path)
                print(f"INFO: Removed old log file: {log_file_path}")
        except (ValueError, IndexError):
            # Ignore files that don't match the 'service-YYYY-MM-DD.log' format
            continue
            
    for file_path in sorted(files_to_delete):
        try:
            os.remove(file_path)
            print(f"Removed old log file: {file_path}")
        except OSError as e:
            print(f"Error removing file {file_path}: {e}")

def setup_logging(level=logging.INFO, container_name:str="unknown_service", log_directory:Path=Path("/app/logs"), execution_mode:str = 'long_running', max_age_of_log_file:TimeDeltaConfig = TimeDeltaConfig()):
    """
    Configures the root logger to send messages to stdout.
    """
    
    root_logger:logging.Logger = logging.getLogger()
    
    if root_logger.handlers:
        return
    
    
    root_logger.setLevel(level)
    if isinstance(log_directory, str):
        log_directory = Path(log_directory)    
    log_directory.mkdir(mode=775,parents=True, exist_ok=True)

    
    if execution_mode == "cron":
        _cleanup_old_logs(log_directory, max_age_of_log_file)
        hour_utc_str = datetime.datetime.utcnow().strftime('%Y-%m-%d-%H-%M')
        log_filename = f"cron-service-{hour_utc_str}.log"
        log_filepath: Path = log_directory / log_filename
        file_handler = logging.FileHandler(str(log_filepath))
        
    elif execution_mode == "long_running":
        log_filename = "service.log"
        log_filepath = log_directory / log_filename
        total_days = max_age_of_log_file.total_days
        backup_count = int(total_days) if total_days >= 1 else 1
        file_handler = TimedRotatingFileHandler(str(log_filepath), when='D', interval=1, backupCount=backup_count, utc=True)    
    else:
        raise ValueError(f"Invalid execution_mode: '{execution_mode}'. Must be 'long_running' or 'cron'.")
        
        
    for logger_name in NOISY_LOGGERS:
        logging.getLogger(logger_name).setLevel(logging.WARNING)

    # Standard format: Time | Level | Logger Name | Message
    log_format = f'%(asctime)s - %(levelname)s - [{container_name}.%(name)s] - %(message)s'
    formatter = logging.Formatter(log_format)
    stream_handler = logging.StreamHandler(sys.stdout)
   
    handlers = [stream_handler, file_handler]

    
    for handler in handlers:
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)
    
    try:
        os.chmod(str(log_filepath), 0o666)
    except OSError as e:
        print(f"Could not set permissions on {log_filepath}: {e}")  
    

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
