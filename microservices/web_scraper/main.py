import logging
import signal
from common.io.logging import setup_logging
from common.models.api.dtos.job import JobType
from common.service.service_template import ServiceConfig
from microservices.web_scraper.config import BACKGROUND_OUTPUT_STREAM, USER_OUTPUT_STREAM
from microservices.web_scraper.scraper_service import ScraperService
from logging import Logger, getLogger, DEBUG

from microservices.web_scraper.config import (
    BACKGROUND_OUTPUT_STREAM,
    BATCH_SIZE,
    CONSUMER_NAME,
    FAILURE_OUTPUT_STREAM,
    GROUP_NAME,
    INPUT_STREAM,
    SCRAPER_MAX_WORKERS,
    USER_OUTPUT_STREAM
)
SERVICE_NAME="scraper"
CONTAINER_NAME="web_scraper"

if __name__ == "__main__":
    setup_logging(level=DEBUG,container_name=CONTAINER_NAME)
    routing_map = {"user": USER_OUTPUT_STREAM, "background": BACKGROUND_OUTPUT_STREAM}
    
    config = ServiceConfig(max_workers=SCRAPER_MAX_WORKERS, BATCH_SIZE=BATCH_SIZE,service_name=SERVICE_NAME, input_streams=[INPUT_STREAM], group_name=GROUP_NAME, CONSUMER_NAME=CONSUMER_NAME, failure_output_stream=FAILURE_OUTPUT_STREAM, routing_map=routing_map,is_concurrent=True, batch_size=BATCH_SIZE )
    scraper_service = ScraperService(config)
    signal.signal(signal.SIGINT, scraper_service.shutdown)
    signal.signal(signal.SIGTERM, scraper_service.shutdown)
    scraper_service.run()
