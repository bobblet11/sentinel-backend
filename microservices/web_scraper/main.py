import logging
import signal
from common.io.logging import setup_logging
from common.models.api.dtos.job import JobType
from common.redis_client.prioritised_consumer_combiner import BlockPrioritisationLevel
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
    INPUT_STREAMS,
    SCRAPER_MAX_WORKERS,
    USER_OUTPUT_STREAM,
    LOG_MODE
)

SERVICE_NAME="scraper"
CONTAINER_NAME="web_scraper"

if __name__ == "__main__":
    setup_logging(level=logging.INFO, container_name=CONTAINER_NAME)

    config = ServiceConfig(
        routing_key=["header","type"],
        max_workers=SCRAPER_MAX_WORKERS, 
        service_name=SERVICE_NAME, 
        input_streams=INPUT_STREAMS, 
        output_streams=[USER_OUTPUT_STREAM, BACKGROUND_OUTPUT_STREAM],
        router_key_values=[JobType.USER.value, JobType.BACKGROUND.value],
        block_prioritisation_level=BlockPrioritisationLevel.EXPONENTIAL,
        group_name=GROUP_NAME, 
        consumer_name=CONSUMER_NAME, 
        failure_output_stream=FAILURE_OUTPUT_STREAM, 
        is_concurrent=True, 
        batch_size=BATCH_SIZE,
        is_cut_and_paste_mode=False
        )
    
    
    
    scraper_service = ScraperService(config)
    signal.signal(signal.SIGINT, scraper_service.shutdown)
    signal.signal(signal.SIGTERM, scraper_service.shutdown)
    scraper_service.run()
