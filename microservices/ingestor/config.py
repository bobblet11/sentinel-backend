from typing import Optional, List
from dotenv import load_dotenv
from common.env.log_env import print_env, Config, EnvVariable
from common.env.get_env_var import get_env_var
from logging import Logger, getLogger
load_dotenv()

config_logger: Logger = getLogger("config")

MAX_INGESTOR_WORKERS: int = get_env_var("MAX_INGESTOR_WORKERS",int, config_logger)
REDIS_DUPLICATE_FILTER_KEY: str = get_env_var("REDIS_DUPLICATE_FILTER_KEY",str, config_logger)
OUTPUT_STREAM: str = get_env_var("OUTPUT_STREAM",str, config_logger)

LOG_MODE: str = get_env_var("LOG_MODE",str, config_logger)

env_variables: List[EnvVariable] = [
    EnvVariable("MAX_INGESTOR_WORKERS", MAX_INGESTOR_WORKERS), 
    EnvVariable("OUTPUT_STREAM", OUTPUT_STREAM), 
    EnvVariable("REDIS_DUPLICATE_FILTER_KEY", REDIS_DUPLICATE_FILTER_KEY),
    EnvVariable("LOG_MODE", LOG_MODE)
]

input_sources:str = "RSS FEEDS"
output_stream:str = OUTPUT_STREAM

print_env(Config(env_variables, input_sources, output_stream), config_logger)
