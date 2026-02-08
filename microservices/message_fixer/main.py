from logging import Logger, getLogger, DEBUG
import signal
from common.io.logging import setup_logging
from common.models.api.dtos.job import JobType
from common.redis_client.prioritised_consumer_combiner import BlockPrioritisationLevel
from common.service.service_template import ServiceConfig
from microservices.message_fixer.fixer import MessageFixerService
from microservices.message_fixer.config import BACKGROUND_OUTPUT_STREAM, BATCH_SIZE, FAILURE_OUTPUT_STREAM, INPUT_STREAMS, GROUP_NAME, CONSUMER_NAME, USER_OUTPUT_STREAM, MESSAGE_FIXER_MAX_WORKERS

SERVICE_NAME = "message_fixer"
# will tranlsate from the old Message Payload, to the newest one. So need to serialise as a dict, and map each key to the new one.
if __name__ == "__main__":
    setup_logging(level=DEBUG, container_name="message_fixer")
    main_logger: Logger = getLogger("__main__")
    
    config = ServiceConfig(
        routing_key=["header","type"], 
        max_workers=MESSAGE_FIXER_MAX_WORKERS, 
        service_name=SERVICE_NAME, 
        input_streams=INPUT_STREAMS, 
        output_streams=[USER_OUTPUT_STREAM, BACKGROUND_OUTPUT_STREAM],
        router_key_values=[JobType.USER.value, JobType.BACKGROUND.value],
        block_prioritisation_level=BlockPrioritisationLevel.EXPONENTIAL,
        group_name=GROUP_NAME, 
        consumer_name=CONSUMER_NAME, 
        failure_output_stream=FAILURE_OUTPUT_STREAM, 
        is_concurrent=False, 
        batch_size=BATCH_SIZE)
    
    fixer_service = MessageFixerService(config, options=None)
    
    signal.signal(signal.SIGINT, fixer_service.shutdown)
    signal.signal(signal.SIGTERM, fixer_service.shutdown)
    
    fixer_service.run()
