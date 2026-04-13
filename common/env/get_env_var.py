import os
from common.env.log_env import EnvVariable
from typing import Type, TypeVar, Any
from logging import Logger


T = TypeVar("T")

def get_env_var(key: str, cast_to: Type[T], logger: Logger, default: Any = None) -> T:
	value = os.getenv(key)

	# 1. Handle Missing or Empty Variables
	if not value:
		if default is not None:
			return default
		logger.error(f"FATAL: {key} environment variable is not set. Exiting.")
		exit(1)

	# 2. Handle Booleans (Special Case)
	if cast_to == bool:
		return value.lower() in ("true", "1", "yes") 

	# 3. Handle Everything Else (int, float, str)
	try:
		return cast_to(value)
	except ValueError:
		logger.error(f"FATAL: {key} is set to '{value}', but expected type {cast_to.__name__}.")
		exit(1)
