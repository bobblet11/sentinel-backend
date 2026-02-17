from typing import List
from dotenv import load_dotenv
from common.env.log_env import print_env, Config, EnvVariable
from common.env.get_env_var import get_env_var
from logging import Logger, getLogger



load_dotenv()
config_logger: Logger = getLogger("config")

# Service Configuration
# API_SERVICE_PORT: int = get_env_var("API_SERVICE_PORT",int, config_logger)

# Postgres Connection Configuration
POSTGRES_HOST: str = get_env_var("POSTGRES_HOST",str, config_logger)
POSTGRES_EXTERNAL_PORT: int = get_env_var("POSTGRES_EXTERNAL_PORT",int, config_logger)
POSTGRES_DB: str = get_env_var("POSTGRES_DB",str, config_logger)
POSTGRES_USER: str = get_env_var("POSTGRES_USER",str, config_logger)
POSTGRES_PASSWORD: str = get_env_var("POSTGRES_PASSWORD",str, config_logger)

# Redis stream configs
INPUT_STREAMS: List[str] = get_env_var(
    "INPUT_STREAMS",
    lambda x: x.split(","),
    config_logger
)

USER_OUTPUT_STREAM: str = get_env_var(
    "USER_OUTPUT_STREAM",
    str,
    config_logger
)

FAILURE_OUTPUT_STREAM: str = get_env_var(
    "FAILURE_OUTPUT_STREAM",
    str,
    config_logger
)
GROUP_NAME: str = get_env_var(
    "GROUP_NAME",
    str,
    config_logger
)
CONSUMER_NAME: str = get_env_var(
    "CONSUMER_NAME",
    str,
    config_logger
)

BATCH_SIZE: int = get_env_var(
    "BATCH_SIZE",
    int,
    config_logger,
    default=10
)

env_variables: List[EnvVariable] = [
    # EnvVariable("API_SERVICE_PORT", API_SERVICE_PORT), 
    
    EnvVariable("POSTGRES_HOST", POSTGRES_HOST), 
    EnvVariable("POSTGRES_EXTERNAL_PORT", POSTGRES_EXTERNAL_PORT),
    EnvVariable("POSTGRES_DB", POSTGRES_DB),
    EnvVariable("POSTGRES_USER", POSTGRES_USER),
    EnvVariable("POSTGRES_PASSWORD", POSTGRES_PASSWORD),
    
        EnvVariable("INPUT_STREAMS", INPUT_STREAMS),
    EnvVariable("USER_OUTPUT_STREAM", USER_OUTPUT_STREAM),
    EnvVariable("FAILURE_OUTPUT_STREAM", FAILURE_OUTPUT_STREAM),
    EnvVariable("GROUP_NAME", GROUP_NAME),
    EnvVariable("CONSUMER_NAME", CONSUMER_NAME),
    EnvVariable("BATCH_SIZE", BATCH_SIZE),
]

output_streams = [USER_OUTPUT_STREAM, FAILURE_OUTPUT_STREAM]

print_env(Config(env_variables, None, output_streams), config_logger)


