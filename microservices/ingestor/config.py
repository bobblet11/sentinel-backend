from logging import Logger, getLogger
from typing import List

from dotenv import load_dotenv

from common.env.get_env_var import get_env_var
from common.env.log_env import Config, EnvVariable, print_env

load_dotenv()

config_logger: Logger = getLogger("config")

MAX_INGESTOR_WORKERS: int = get_env_var("MAX_INGESTOR_WORKERS",int, config_logger)
REDIS_DUPLICATE_FILTER_KEY: str = get_env_var("REDIS_DUPLICATE_FILTER_KEY",str, config_logger)
OUTPUT_STREAM: str = get_env_var("OUTPUT_STREAM",str, config_logger)


# Postgres Connection Configuration
POSTGRES_HOST: str = get_env_var("POSTGRES_HOST",str, config_logger)
POSTGRES_PORT: int = get_env_var("POSTGRES_PORT",int, config_logger)
POSTGRES_DB: str = get_env_var("POSTGRES_DB",str, config_logger)
POSTGRES_USER: str = get_env_var("POSTGRES_USER",str, config_logger)
POSTGRES_PASSWORD: str = get_env_var("POSTGRES_PASSWORD",str, config_logger)
POSTGRES_SSLMODE: str = get_env_var("POSTGRES_SSLMODE", str, config_logger, default="disable")

LOG_MODE: int = get_env_var("LOG_MODE",int, config_logger)

env_variables: List[EnvVariable] = [
    EnvVariable("MAX_INGESTOR_WORKERS", MAX_INGESTOR_WORKERS), 
    EnvVariable("OUTPUT_STREAM", OUTPUT_STREAM), 
    EnvVariable("REDIS_DUPLICATE_FILTER_KEY", REDIS_DUPLICATE_FILTER_KEY),
    EnvVariable("LOG_MODE", LOG_MODE),
    
    EnvVariable("POSTGRES_HOST", POSTGRES_HOST), 
    EnvVariable("POSTGRES_PORT", POSTGRES_PORT),
    EnvVariable("POSTGRES_DB", POSTGRES_DB),
    EnvVariable("POSTGRES_USER", POSTGRES_USER),
    EnvVariable("POSTGRES_PASSWORD", POSTGRES_PASSWORD),
]

input_sources:str = "RSS FEEDS"
output_stream:str = OUTPUT_STREAM

print_env(Config(env_variables, input_sources, output_stream), config_logger)
