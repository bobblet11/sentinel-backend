from typing import Optional, List
from dotenv import load_dotenv
from common.env.log_env import print_env, Config, EnvVariable
from common.env.get_env_var import get_env_var
from logging import Logger, getLogger
load_dotenv()
config_logger: Logger = getLogger("config")

PRIORITY_MAP = {
    "user": 1,
    "admin": 1,  # Same priority as user
    "background": 2,
    "logging": 3,
}
LOWEST_PRIORITY: float = float("inf")

INPUT_STREAM: str = get_env_var("INPUT_STREAM",str, config_logger)
USER_OUTPUT_STREAM: str = get_env_var("USER_OUTPUT_STREAM",str, config_logger)
BACKGROUND_OUTPUT_STREAM: str = get_env_var("BACKGROUND_OUTPUT_STREAM",str, config_logger)
FAILURE_OUTPUT_STREAM: str = get_env_var("FAILURE_OUTPUT_STREAM",str, config_logger)

GROUP_NAME: str = get_env_var("GROUP_NAME",str, config_logger)
CONSUMER_NAME: str = get_env_var("CONSUMER_NAME",str, config_logger)

WEBSHARIO_URL: str = get_env_var("WEBSHARIO_URL",str, config_logger)

BATCH_SIZE: int = get_env_var("BATCH_SIZE",int, config_logger)
SCRAPER_MAX_WORKERS: int = get_env_var("SCRAPER_MAX_WORKERS",int, config_logger)
MAX_PROXY_VALIDATION_WORKERS: int = get_env_var("MAX_PROXY_VALIDATION_WORKERS",int, config_logger)
MAX_FETCH_RETRIES: int = get_env_var("MAX_FETCH_RETRIES",int, config_logger)
INITIAL_FETCH_DELAY_S: float = get_env_var("INITIAL_FETCH_DELAY_S",float, config_logger)
FETCH_DELAY_GROWTH_RATE: float = get_env_var("FETCH_DELAY_GROWTH_RATE",float, config_logger)


env_variables: List[EnvVariable] = [
    EnvVariable("LOWEST_PRIORITY", LOWEST_PRIORITY), 
    EnvVariable("PRIORITY_MAP", PRIORITY_MAP), 
    
    EnvVariable("INPUT_STREAM", INPUT_STREAM),
    EnvVariable("USER_OUTPUT_STREAM", USER_OUTPUT_STREAM),
    EnvVariable("BACKGROUND_OUTPUT_STREAM", BACKGROUND_OUTPUT_STREAM),
    EnvVariable("FAILURE_OUTPUT_STREAM", FAILURE_OUTPUT_STREAM),
    
    EnvVariable("GROUP_NAME", GROUP_NAME),
    EnvVariable("CONSUMER_NAME", CONSUMER_NAME), 
    
    EnvVariable("WEBSHARIO_URL", WEBSHARIO_URL), 
    
    EnvVariable("BATCH_SIZE", BATCH_SIZE), 
    EnvVariable("SCRAPER_MAX_WORKERS", SCRAPER_MAX_WORKERS), 
    EnvVariable("MAX_PROXY_VALIDATION_WORKERS", MAX_PROXY_VALIDATION_WORKERS), 
    EnvVariable("MAX_FETCH_RETRIES", MAX_FETCH_RETRIES), 
    EnvVariable("INITIAL_FETCH_DELAY_S", INITIAL_FETCH_DELAY_S), 
    EnvVariable("FETCH_DELAY_GROWTH_RATE", FETCH_DELAY_GROWTH_RATE), 
]

input_stream:str = INPUT_STREAM
output_streams:List[str] = [USER_OUTPUT_STREAM, BACKGROUND_OUTPUT_STREAM, FAILURE_OUTPUT_STREAM]

print_env(Config(env_variables, input_stream, output_streams), config_logger)
