from logging import Logger, getLogger
from typing import List

from dotenv import load_dotenv

from common.env.get_env_var import get_env_var
from common.env.log_env import Config, EnvVariable, print_env

load_dotenv()
config_logger: Logger = getLogger("config")

# Service Configuration
API_SERVICE_PORT: int = get_env_var("API_SERVICE_PORT", int, config_logger)

# Postgres Connection Configuration
POSTGRES_HOST: str = get_env_var("POSTGRES_HOST", str, config_logger)
POSTGRES_PORT: int = get_env_var("POSTGRES_PORT", int, config_logger)
POSTGRES_DB: str = get_env_var("POSTGRES_DB", str, config_logger)
POSTGRES_USER: str = get_env_var("POSTGRES_USER", str, config_logger)
POSTGRES_PASSWORD: str = get_env_var("POSTGRES_PASSWORD", str, config_logger)
POSTGRES_SSLMODE: str = get_env_var(
    "POSTGRES_SSLMODE", str, config_logger, default="disable"
)

# Redis stream configs
OUTPUT_STREAM: str = get_env_var("OUTPUT_STREAM", str, config_logger)
HASH_STORE_NAMESPACE: str = get_env_var("HASH_STORE_NAMESPACE", str, config_logger)

env_variables: List[EnvVariable] = [
    EnvVariable("API_SERVICE_PORT", API_SERVICE_PORT),
    EnvVariable("POSTGRES_HOST", POSTGRES_HOST),
    EnvVariable("POSTGRES_PORT", POSTGRES_PORT),
    EnvVariable("POSTGRES_DB", POSTGRES_DB),
    EnvVariable("POSTGRES_USER", POSTGRES_USER),
    EnvVariable("POSTGRES_PASSWORD", POSTGRES_PASSWORD),
    EnvVariable("OUTPUT_STREAM", OUTPUT_STREAM),
    EnvVariable("HASH_STORE_NAMESPACE", HASH_STORE_NAMESPACE),
]


print_env(Config(env_variables, None, None), config_logger)
