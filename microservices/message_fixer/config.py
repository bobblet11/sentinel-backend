from typing import  List
from dotenv import load_dotenv
from common.env.log_env import print_env, Config, EnvVariable
from common.env.get_env_var import get_env_var
from logging import Logger, getLogger
load_dotenv()

config_logger: Logger = getLogger("config")

INPUT_STREAMS: List[str] = get_env_var("INPUT_STREAMS",str, config_logger).split(", ")
USER_OUTPUT_STREAM: str = get_env_var("USER_OUTPUT_STREAM",str, config_logger)
BACKGROUND_OUTPUT_STREAM: str = get_env_var("BACKGROUND_OUTPUT_STREAM",str, config_logger)
FAILURE_OUTPUT_STREAM: str = get_env_var("FAILURE_OUTPUT_STREAM",str, config_logger)

GROUP_NAME: str = get_env_var("GROUP_NAME",str, config_logger)
CONSUMER_NAME: str = get_env_var("CONSUMER_NAME",str, config_logger)
MESSAGE_FIXER_MAX_WORKERS: int  = get_env_var("MESSAGE_FIXER_MAX_WORKERS",str, config_logger)
BATCH_SIZE: int = get_env_var("BATCH_SIZE", int, config_logger)

input_streams: List[str] = INPUT_STREAMS
output_streams:str = [USER_OUTPUT_STREAM, BACKGROUND_OUTPUT_STREAM, FAILURE_OUTPUT_STREAM]

env_variables: List[EnvVariable] = [
    EnvVariable("INPUT_STREAMS", INPUT_STREAMS),
    EnvVariable("USER_OUTPUT_STREAM", USER_OUTPUT_STREAM),
    EnvVariable("BACKGROUND_OUTPUT_STREAM", BACKGROUND_OUTPUT_STREAM),
    EnvVariable("FAILURE_OUTPUT_STREAM", FAILURE_OUTPUT_STREAM),
    EnvVariable("GROUP_NAME", GROUP_NAME), 
    EnvVariable("CONSUMER_NAME", CONSUMER_NAME), 
    EnvVariable("MESSAGE_FIXER_MAX_WORKERS", MESSAGE_FIXER_MAX_WORKERS), 
    EnvVariable("BATCH_SIZE", BATCH_SIZE), 
]

print_env(Config(env_variables, input_streams, output_streams), config_logger)
