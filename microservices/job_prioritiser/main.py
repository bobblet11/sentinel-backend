import signal
from logging import Logger, getLogger, DEBUG
from common.io.logging import setup_logging
from common.models.api.dtos.job import JobType
from common.service.service_template import ServiceConfig
from microservices.job_prioritiser.prioritiser_service import PrioritiserService

from .config import (
    BATCH_SIZE,
    CONSUMER_NAME,
    GROUP_NAME,
    INPUT_STREAMS,
    OUTPUT_STREAM,
    FAILURE_OUTPUT_STREAM
)

if __name__ == "__main__":
    setup_logging(level=DEBUG, container_name=CONSUMER_NAME)
    main_logger: Logger = getLogger("__main__")
    routing_map = {JobType.BACKGROUND.value: OUTPUT_STREAM, JobType.USER.value: OUTPUT_STREAM}
    main_logger.info(routing_map)
    
    config = ServiceConfig(service_name=CONSUMER_NAME, input_streams=INPUT_STREAMS, group_name=GROUP_NAME, consumer_name=CONSUMER_NAME, failure_output_stream=FAILURE_OUTPUT_STREAM, routing_map=routing_map, is_concurrent=False, batch_size=BATCH_SIZE )
    prioritiser = PrioritiserService(config)

    signal.signal(signal.SIGINT, prioritiser.shutdown)
    signal.signal(signal.SIGTERM, prioritiser.shutdown)

    prioritiser.run()
