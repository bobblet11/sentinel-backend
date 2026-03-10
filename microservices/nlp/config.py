from typing import  List
from dotenv import load_dotenv
from common.env.log_env import print_env, Config, EnvVariable
from common.env.get_env_var import get_env_var
from logging import Logger, getLogger
load_dotenv()

config_logger: Logger = getLogger("config")

INPUT_STREAMS: List[str] = [x.strip(" ,") for x in get_env_var("INPUT_STREAMS",str, config_logger).split(",")]
USER_OUTPUT_STREAM: str = get_env_var("USER_OUTPUT_STREAM",str, config_logger)
BACKGROUND_OUTPUT_STREAM: str = get_env_var("BACKGROUND_OUTPUT_STREAM",str, config_logger)
FAILURE_OUTPUT_STREAM: str = get_env_var("FAILURE_OUTPUT_STREAM",str, config_logger)

GROUP_NAME: str = get_env_var("GROUP_NAME",str, config_logger)
CONSUMER_NAME: str = get_env_var("CONSUMER_NAME",str, config_logger)
NLP_MAX_WORKERS: int  = get_env_var("NLP_MAX_WORKERS",str, config_logger)
BATCH_SIZE: int = get_env_var("BATCH_SIZE", int, config_logger)

DUMMY_NLP_MODE: bool = get_env_var(
    "DUMMY_NLP_MODE",
    lambda x: str(x).lower() in {"1", "true", "yes", "y"},
    config_logger,
    default=False,
)

EMBEDDING_MODEL = get_env_var("NLP_EMBEDDING_MODEL", str, config_logger, "sentence-transformers/all-mpnet-base-v2")
NER_MODEL = get_env_var("NLP_NER_MODEL", str, config_logger, "dslim/bert-base-NER")
BIAS_MODEL = get_env_var("NLP_BIAS_MODEL", str, config_logger, "facebook/bart-large-mnli")
CHECKWORTHY_MODEL = get_env_var("NLP_CHECKWORTHY_MODEL", str, config_logger, "valhalla/distilbart-mnli-12-3")
CHECKWORTHY_BATCH_SIZE: int = get_env_var("NLP_CHECKWORTHY_BATCH_SIZE", int, config_logger, 16)
MAX_SENTENCES_FOR_CHECKWORTHY: int = get_env_var("NLP_MAX_SENTENCES_FOR_CHECKWORTHY", int, config_logger, 40)
NER_MAX_TEXT_CHARS: int = get_env_var("NLP_NER_MAX_TEXT_CHARS", int, config_logger, 3000)
DEVICE = "cuda" if get_env_var("USE_GPU", str, config_logger, "false").lower() == "true" else "cpu"

input_streams: List[str] = INPUT_STREAMS
output_streams:str = [USER_OUTPUT_STREAM, BACKGROUND_OUTPUT_STREAM, FAILURE_OUTPUT_STREAM]

env_variables: List[EnvVariable] = [
    EnvVariable("INPUT_STREAMS", INPUT_STREAMS),
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
    EnvVariable("CHECKWORTHY_MODEL", CHECKWORTHY_MODEL),
    EnvVariable("CHECKWORTHY_BATCH_SIZE", CHECKWORTHY_BATCH_SIZE),
    EnvVariable("MAX_SENTENCES_FOR_CHECKWORTHY", MAX_SENTENCES_FOR_CHECKWORTHY),
    EnvVariable("NER_MAX_TEXT_CHARS", NER_MAX_TEXT_CHARS),
    EnvVariable("DEVICE", DEVICE),
    EnvVariable("DUMMY_NLP_MODE", DUMMY_NLP_MODE),
]

print_env(Config(env_variables, input_streams, output_streams), config_logger)
