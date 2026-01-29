from logging import Logger, getLogger, DEBUG
import signal
from common.io.logging import setup_logging
from common.models.api.dtos.job import JobType
from common.service.service_template import ServiceConfig
from microservices.nlp.config import BACKGROUND_OUTPUT_STREAM, BATCH_SIZE, FAILURE_OUTPUT_STREAM, INPUT_STREAM, GROUP_NAME, CONSUMER_NAME, USER_OUTPUT_STREAM
from microservices.nlp.nlp_service import NLPService

SERVICE_NAME = "NLP"

if __name__ == "__main__":
    setup_logging(level=DEBUG, container_name="nlp")
    main_logger: Logger = getLogger("__main__")
    routing_map = {JobType.USER.value: USER_OUTPUT_STREAM, JobType.BACKGROUND.value: BACKGROUND_OUTPUT_STREAM}
    
    config = ServiceConfig(routing_key=["header","type"], max_workers=1, service_name=SERVICE_NAME, input_streams=[INPUT_STREAM], group_name=GROUP_NAME, consumer_name=CONSUMER_NAME, failure_output_stream=FAILURE_OUTPUT_STREAM, routing_map=routing_map, is_concurrent=False, batch_size=BATCH_SIZE )
    nlp_service = NLPService(config, options=None)
    
    signal.signal(signal.SIGINT, nlp_service.shutdown)
    signal.signal(signal.SIGTERM, nlp_service.shutdown)
    
    nlp_service.run()
