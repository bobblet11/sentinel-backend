from common.redis_client.publisher import RedisPublisher
from common.models.api.redis_models import (
    Message,
    MessageHeader,
    MessageURLPayload
)
from datetime import datetime
import uuid
from microservices.api_gateway.config import JOB_STREAM


class QueueService:
    def __init__(self):
        self._publisher: RedisPublisher | None = None

    def _get_publisher(self) -> RedisPublisher:
        if self._publisher is None:
            self._publisher = RedisPublisher(stream_name=JOB_STREAM)
        return self._publisher

    def publish_analysis_job(self, job_id: str, url: str, content: str):
        message = Message(
            header=MessageHeader(
                message_id=str(uuid.uuid4()),
                timestamp=datetime.utcnow().isoformat(),
                type="analysis"
            ),
            data=MessageURLPayload(
                url=url,
                content=content,
                source_rss="browser-extension"
            )
        )

        publisher = self._get_publisher()
        publisher.publish_one(message.dict())
