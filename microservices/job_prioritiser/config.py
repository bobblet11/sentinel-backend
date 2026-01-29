from typing import Optional, List
from dotenv import load_dotenv
from common.env.log_env import print_env, Config, EnvVariable
from common.env.get_env_var import get_env_var
from logging import Logger, getLogger
load_dotenv()

config_logger: Logger = getLogger("config")
INPUT_STREAMS_: str = get_env_var("INPUT_STREAMS",str, config_logger)
OUTPUT_STREAM: str = get_env_var("OUTPUT_STREAM",str, config_logger)
GROUP_NAME: str = get_env_var("GROUP_NAME",str, config_logger)
CONSUMER_NAME: str = get_env_var("CONSUMER_NAME",str, config_logger)
INPUT_STREAMS: List[str] = (INPUT_STREAMS_).split(", ")
BATCH_SIZE: int = get_env_var("BATCH_SIZE", int, config_logger)
MAX_PUBLISH_WORKERS: int = get_env_var("MAX_PUBLISH_WORKERS", int, config_logger)
FAILURE_OUTPUT_STREAM: str = get_env_var("FAILURE_OUTPUT_STREAM",str, config_logger)

env_variables: List[EnvVariable] = [
    EnvVariable("INPUT_STREAMS", INPUT_STREAMS_),
    EnvVariable("OUTPUT_STREAM", OUTPUT_STREAM), 
    EnvVariable("FAILURE_OUTPUT_STREAM", FAILURE_OUTPUT_STREAM), 
    EnvVariable("GROUP_NAME", GROUP_NAME), 
    EnvVariable("CONSUMER_NAME", CONSUMER_NAME), 
    EnvVariable("BATCH_SIZE", BATCH_SIZE), 
    EnvVariable("MAX_PUBLISH_WORKERS", MAX_PUBLISH_WORKERS), 

]

input_sources:str = INPUT_STREAMS
output_stream:str = OUTPUT_STREAM

print_env(Config(env_variables, input_sources, output_stream), config_logger)
