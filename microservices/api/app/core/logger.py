from logging import DEBUG, Logger, getLogger

from common.io.logging import setup_logging

CONTAINER_NAME="API"
setup_logging(level=DEBUG,container_name=CONTAINER_NAME)
logger:Logger = getLogger("API")
