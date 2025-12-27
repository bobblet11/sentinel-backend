from typing import List, Any
from logging import Logger
from dataclasses import dataclass

@dataclass(frozen=True)
class EnvVariable:
        name: str	
        value: any

@dataclass(frozen=True)
class Config:
        environment_variables: List[EnvVariable]
        input_stream: str | List[str] | None
        output_stream: str | List[str] | None

def print_env(
	config: Config,
	logger: Logger
) -> None:
	for variable in config.environment_variables:
		logger.info(f"{variable.name} = {variable.value}\n")

	if config.input_stream:
		logger.info("-" * 9)
		logger.info(config.input_stream)
		logger.info("-" * 9)

	logger.info("    |    \n    V    ")

	if config.output_stream:
		logger.info("-" * 9)
		logger.info(config.output_stream)
		logger.info("-" * 9)

