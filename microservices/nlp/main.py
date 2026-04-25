import signal
from logging import Logger, getLogger

from common.io.logging import setup_logging
from common.models.api.dtos.job import JobType
from common.redis_client.prioritised_consumer_combiner import \
    BlockPrioritisationLevel
from common.service.service_template import ServiceConfig
from microservices.nlp.config import (BACKGROUND_OUTPUT_STREAM, BATCH_SIZE,
                                      CONSUMER_NAME, FAILURE_OUTPUT_STREAM,
                                      GROUP_NAME, INPUT_STREAMS, LOG_MODE,
                                      NLP_MAX_WORKERS, USER_OUTPUT_STREAM)
from microservices.nlp.nlp_service import NLPService

SERVICE_NAME = "NLP"

if __name__ == "__main__":
    setup_logging(level=LOG_MODE, container_name="nlp")
    main_logger: Logger = getLogger("__main__")
    
    config = ServiceConfig(
        service_name=SERVICE_NAME, 
        input_streams=INPUT_STREAMS, 
        output_streams=[USER_OUTPUT_STREAM, BACKGROUND_OUTPUT_STREAM],
        routing_key=["header","type"], 
        group_name=GROUP_NAME, 
        consumer_name=CONSUMER_NAME, 
        block_prioritisation_level=BlockPrioritisationLevel.EXPONENTIAL,
        failure_output_stream=FAILURE_OUTPUT_STREAM, 
        router_key_values=[JobType.USER.value, JobType.BACKGROUND.value],
        is_concurrent=True if int(NLP_MAX_WORKERS) > 1 else False,
        max_workers=int(NLP_MAX_WORKERS),    
        
        batch_size=BATCH_SIZE,
        is_cut_and_paste_mode=True, #delete job on ack
        retry_failure_mode=False #if input stream is empty, retry jobs in failure mode. Turn on after fixing failed jobs.
    )
    
    nlp_service = NLPService(config, options=None)
    
    signal.signal(signal.SIGINT, nlp_service.shutdown)
    signal.signal(signal.SIGTERM, nlp_service.shutdown)
    
    nlp_service.run()
