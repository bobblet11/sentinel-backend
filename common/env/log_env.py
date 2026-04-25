from dataclasses import dataclass
from logging import Logger
from typing import List


@dataclass(frozen=True)
class EnvVariable:
    name: str
    value: any


@dataclass(frozen=True)
class Config:
    environment_variables: List[EnvVariable]
    input_stream: str | List[str] | None
    output_stream: str | List[str] | None


def print_env(config: Config, logger: Logger) -> None:
    for variable in config.environment_variables:
        logger.info(f"{variable.name} = {variable.value}")

    if config.input_stream:
        logger.info(f"input_stream: {config.input_stream}")

    if config.output_stream:
        logger.info(f"output_stream: {config.output_stream}")
