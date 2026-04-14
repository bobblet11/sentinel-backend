import signal
from logging import INFO

from common.io.logging import setup_logging
from common.models.api.dtos.job import JobType
from common.service.service_template import ServiceConfig
from common.redis_client.prioritised_consumer_combiner import BlockPrioritisationLevel

from microservices.retrieval_layer.services.retrieval_service import RetrievalService
from microservices.retrieval_layer.config import (
    INPUT_STREAMS,
    FAILURE_OUTPUT_STREAM,
    GROUP_NAME,
    CONSUMER_NAME,
    BATCH_SIZE,
    RETRY_FAILURE_MODE,
    LOG_MODE,
    BENCHMARK_OUTPUT_STREAM,
    IS_BENCHMARK,
    MAX_WORKERS
)
from microservices.retrieval_layer.db.session import ensure_schema_compatibility

SERVICE_NAME = "retrieval"
CONTAINER_NAME = "retrieval-layer"

if __name__ == "__main__":
    setup_logging(level=LOG_MODE, container_name=CONTAINER_NAME)
    print(IS_BENCHMARK)
    print(BENCHMARK_OUTPUT_STREAM)
    config = ServiceConfig(
        service_name=SERVICE_NAME,
                
        input_streams=INPUT_STREAMS, # user:to.be.retrieval, background:to.be.retrieval
        failure_output_stream=FAILURE_OUTPUT_STREAM,
        output_streams=[BENCHMARK_OUTPUT_STREAM,BENCHMARK_OUTPUT_STREAM] if IS_BENCHMARK else [],  
        
        routing_key=["header","type"],     
        router_key_values=[JobType.USER.value, JobType.BACKGROUND.value],
        block_prioritisation_level=BlockPrioritisationLevel.EXPONENTIAL,
        group_name=GROUP_NAME,
        consumer_name=CONSUMER_NAME,
        
        is_concurrent=True if MAX_WORKERS > 1 else False,
        max_workers=MAX_WORKERS,                 
        batch_size=BATCH_SIZE,
        is_cut_and_paste_mode=True,
        retry_failure_mode=RETRY_FAILURE_MODE
    )
    print(config.output_streams)
    ensure_schema_compatibility()
    retrieval_service = RetrievalService(config)

    signal.signal(signal.SIGINT, retrieval_service.shutdown)
    signal.signal(signal.SIGTERM, retrieval_service.shutdown)
    retrieval_service.run()
