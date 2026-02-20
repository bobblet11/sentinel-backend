import signal
from logging import DEBUG

from common.io.logging import setup_logging
from common.service.service_template import ServiceConfig
from common.redis_client.prioritised_consumer_combiner import BlockPrioritisationLevel

from microservices.retrieval_layer.services.retrieval_service import RetrievalService
from microservices.retrieval_layer.config import (
    INPUT_STREAMS,
    USER_OUTPUT_STREAM,
    FAILURE_OUTPUT_STREAM,
    GROUP_NAME,
    CONSUMER_NAME,
    BATCH_SIZE,
)

SERVICE_NAME = "retrieval"
CONTAINER_NAME = "retrieval-layer"

if __name__ == "__main__":
    setup_logging(level=DEBUG, container_name=CONTAINER_NAME)

    config = ServiceConfig(
        routing_key=["header","type"],                     
        max_workers=1,                        
        service_name=SERVICE_NAME,
        input_streams=INPUT_STREAMS,# user:to.be.retrieval
        
        output_streams=[USER_OUTPUT_STREAM],  
        router_key_values=["user"],
        
        block_prioritisation_level=BlockPrioritisationLevel.LINEAR,
        group_name=GROUP_NAME,
        consumer_name=CONSUMER_NAME,
        failure_output_stream=FAILURE_OUTPUT_STREAM,
        is_concurrent=False,
        batch_size=BATCH_SIZE,
    )

    retrieval_service = RetrievalService(config)

    signal.signal(signal.SIGINT, retrieval_service.shutdown)
    signal.signal(signal.SIGTERM, retrieval_service.shutdown)
    retrieval_service.run()
