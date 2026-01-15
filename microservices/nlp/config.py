from typing import  List
from dotenv import load_dotenv
from common.env.log_env import print_env, Config, EnvVariable
from common.env.get_env_var import get_env_var
from logging import Logger, getLogger
load_dotenv()

config_logger: Logger = getLogger("config")

INPUT_STREAM: str = get_env_var("INPUT_STREAM",str, config_logger)
USER_OUTPUT_STREAM: str = get_env_var("USER_OUTPUT_STREAM",str, config_logger)
BACKGROUND_OUTPUT_STREAM: str = get_env_var("BACKGROUND_OUTPUT_STREAM",str, config_logger)
FAILURE_OUTPUT_STREAM: str = get_env_var("FAILURE_OUTPUT_STREAM",str, config_logger)

GROUP_NAME: str = get_env_var("GROUP_NAME",str, config_logger)
CONSUMER_NAME: str = get_env_var("CONSUMER_NAME",str, config_logger)
NLP_MAX_WORKERS: int  = get_env_var("NLP_MAX_WORKERS",str, config_logger)
BATCH_SIZE: int = get_env_var("BATCH_SIZE", int, config_logger)
MAX_PUBLISH_WORKERS: int = get_env_var("MAX_PUBLISH_WORKERS", int, config_logger)

# Embedding Model: optimized for semantic search (384 dimensions)
# Matches the 'vector(384)' requirement for pgvector
EMBEDDING_MODEL = get_env_var("NLP_EMBEDDING_MODEL", str, config_logger, "all-MiniLM-L6-v2") 
# NER Model: Standard BERT-based NER
NER_MODEL = get_env_var("NLP_NER_MODEL", str, config_logger, "dslim/bert-base-NER") 
# Bias/Zero-Shot Model: For political leaning and tone
# 'facebook/bart-large-mnli' is great for zero-shot classification
BIAS_MODEL = get_env_var("NLP_BIAS_MODEL", str, config_logger, "facebook/bart-large-mnli") 
# Device selection (cuda if available, else cpu)
DEVICE = "cuda" if get_env_var("USE_GPU", str, config_logger, "false").lower() == "true" else "cpu"

input_source:str = INPUT_STREAM
output_streams:str = [USER_OUTPUT_STREAM, BACKGROUND_OUTPUT_STREAM, FAILURE_OUTPUT_STREAM]

env_variables: List[EnvVariable] = [
    EnvVariable("INPUT_STREAM", INPUT_STREAM),
    EnvVariable("USER_OUTPUT_STREAM", USER_OUTPUT_STREAM),
    EnvVariable("BACKGROUND_OUTPUT_STREAM", BACKGROUND_OUTPUT_STREAM),
    EnvVariable("FAILURE_OUTPUT_STREAM", FAILURE_OUTPUT_STREAM),
    EnvVariable("GROUP_NAME", GROUP_NAME), 
    EnvVariable("CONSUMER_NAME", CONSUMER_NAME), 
    EnvVariable("NLP_MAX_WORKERS", NLP_MAX_WORKERS), 
    EnvVariable("BATCH_SIZE", BATCH_SIZE), 
    EnvVariable("EMBEDDING_MODEL", EMBEDDING_MODEL), 
    EnvVariable("NER_MODEL", NER_MODEL), 
    EnvVariable("BIAS_MODEL", BIAS_MODEL), 
    EnvVariable("DEVICE", DEVICE)
]

print_env(Config(env_variables, input_source, output_streams), config_logger)
