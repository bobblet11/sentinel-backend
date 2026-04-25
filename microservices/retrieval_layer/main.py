import signal

from common.io.logging import setup_logging
from common.models.api.dtos.job import JobType
from common.redis_client.prioritised_consumer_combiner import BlockPrioritisationLevel
from common.service.service_template import ServiceConfig
from microservices.retrieval_layer.config import (
    BATCH_SIZE,
    BENCHMARK_OUTPUT_STREAM,
    CONSUMER_NAME,
    FAILURE_OUTPUT_STREAM,
    GROUP_NAME,
    INPUT_STREAMS,
    IS_BENCHMARK,
    LOG_MODE,
    MAX_WORKERS,
    OUTPUT_STREAM,
    RETRY_FAILURE_MODE,
)
from microservices.retrieval_layer.db.session import ensure_schema_compatibility
from microservices.retrieval_layer.services.retrieval_service import RetrievalService

SERVICE_NAME = "retrieval"
CONTAINER_NAME = "retrieval-layer"

if __name__ == "__main__":
    setup_logging(level=LOG_MODE, container_name=CONTAINER_NAME)

    output_streams = (
        [BENCHMARK_OUTPUT_STREAM, BENCHMARK_OUTPUT_STREAM]
        if IS_BENCHMARK
        else [OUTPUT_STREAM, OUTPUT_STREAM]
    )

    config = ServiceConfig(
        service_name=SERVICE_NAME,
        input_streams=INPUT_STREAMS,  # user:to.be.retrieval, background:to.be.retrieval
        failure_output_stream=FAILURE_OUTPUT_STREAM,
        output_streams=output_streams,
        routing_key=["header", "type"],
        router_key_values=[JobType.USER.value, JobType.BACKGROUND.value],
        block_prioritisation_level=BlockPrioritisationLevel.EXPONENTIAL,
        group_name=GROUP_NAME,
        consumer_name=CONSUMER_NAME,
        is_concurrent=True if MAX_WORKERS > 1 else False,
        max_workers=MAX_WORKERS,
        batch_size=BATCH_SIZE,
        is_cut_and_paste_mode=True,
        retry_failure_mode=RETRY_FAILURE_MODE,
    )
    print(config.output_streams)
    ensure_schema_compatibility()
    retrieval_service = RetrievalService(config)

    signal.signal(signal.SIGINT, retrieval_service.shutdown)
    signal.signal(signal.SIGTERM, retrieval_service.shutdown)
    retrieval_service.run()
