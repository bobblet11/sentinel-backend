from typing import List
from dotenv import load_dotenv
from common.env.log_env import print_env, Config, EnvVariable
from common.env.get_env_var import get_env_var
from logging import Logger, getLogger



load_dotenv()
config_logger: Logger = getLogger("config")

# Service Configuration
LOG_MODE: int = get_env_var("LOG_MODE", int, config_logger, default=10)

# Postgres Connection Configuration
POSTGRES_HOST: str = get_env_var("POSTGRES_HOST", str, config_logger)
POSTGRES_PORT: int = get_env_var("POSTGRES_PORT", int, config_logger)
POSTGRES_DB: str = get_env_var("POSTGRES_DB", str, config_logger)
POSTGRES_USER: str = get_env_var("POSTGRES_USER", str, config_logger)
POSTGRES_PASSWORD: str = get_env_var("POSTGRES_PASSWORD", str, config_logger)
POSTGRES_SSLMODE: str = get_env_var("POSTGRES_SSLMODE", str, config_logger, default="disable")

# Redis stream configs
INPUT_STREAMS: List[str] = [x.strip(" ,") for x in get_env_var("INPUT_STREAMS",str, config_logger).split(",")]

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

RETRY_FAILURE_MODE: bool = get_env_var(
    "RETRIEVAL_RETRY_FAILURE_MODE",
    lambda x: str(x).lower() in {"1", "true", "yes", "y"},
    config_logger,
    default=False,
)

DUMMY_NLP_MODE: bool = get_env_var(
    "DUMMY_NLP_MODE",
    lambda x: str(x).lower() in {"1", "true", "yes", "y"},
    config_logger,
    default=False,
)

DUMMY_SEED_MODE: bool = get_env_var(
    "DUMMY_SEED_MODE",
    lambda x: str(x).lower() in {"1", "true", "yes", "y"},
    config_logger,
    default=False,
)

MAX_WORKERS: int = get_env_var(
    "MAX_WORKERS",
    int,
    config_logger,
    default=1
)

HASH_STORE_NAMESPACE: str = get_env_var("HASH_STORE_NAMESPACE",str, config_logger)
UID_STORE_NAMESPACE: str = get_env_var("UID_STORE_NAMESPACE",str, config_logger)
TEST_MODE: bool = False

IS_BENCHMARK: bool = get_env_var(
    "IS_BENCHMARK",
    lambda x: str(x).lower() in {"1", "true", "yes", "y"},
    config_logger,
    default=False,
)
BENCHMARK_OUTPUT_STREAM: str = get_env_var("BENCHMARK_OUTPUT_STREAM",str, config_logger)

env_variables: List[EnvVariable] = [
    EnvVariable("IS_BENCHMARK", IS_BENCHMARK),
    EnvVariable("BENCHMARK_OUTPUT_STREAM", BENCHMARK_OUTPUT_STREAM),
    EnvVariable("LOG_MODE", LOG_MODE),
    
    EnvVariable("POSTGRES_HOST", POSTGRES_HOST),
    EnvVariable("POSTGRES_PORT", POSTGRES_PORT),
    EnvVariable("POSTGRES_DB", POSTGRES_DB),
    EnvVariable("POSTGRES_USER", POSTGRES_USER),
    EnvVariable("POSTGRES_PASSWORD", POSTGRES_PASSWORD),
    
    EnvVariable("INPUT_STREAMS", INPUT_STREAMS),
    EnvVariable("FAILURE_OUTPUT_STREAM", FAILURE_OUTPUT_STREAM),
    EnvVariable("GROUP_NAME", GROUP_NAME),
    EnvVariable("CONSUMER_NAME", CONSUMER_NAME),
    EnvVariable("HASH_STORE_NAMESPACE", HASH_STORE_NAMESPACE),
    EnvVariable("UID_STORE_NAMESPACE", UID_STORE_NAMESPACE),
    
    EnvVariable("BATCH_SIZE", BATCH_SIZE),
    EnvVariable("MAX_WORKERS", MAX_WORKERS),
    EnvVariable("RETRIEVAL_RETRY_FAILURE_MODE", RETRY_FAILURE_MODE),
    
    EnvVariable("DUMMY_NLP_MODE", DUMMY_NLP_MODE),
    EnvVariable("DUMMY_SEED_MODE", DUMMY_SEED_MODE),
    
    
]

input_streams = INPUT_STREAMS
output_streams = [FAILURE_OUTPUT_STREAM, HASH_STORE_NAMESPACE]

print_env(Config(env_variables, input_streams, output_streams), config_logger)


