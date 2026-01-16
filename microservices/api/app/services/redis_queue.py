import datetime
import hashlib
from common.models.api.redis_models import Message, MessageHeader, MessageURLPayload
from common.redis_client.consumer import RedisConsumer
from common.redis_client.publisher_router import RedisPublisherRouter
from microservices.api.app.core.config import BACKGROUND_OUTPUT_STREAM, USER_OUTPUT_STREAM
from microservices.api.app.dtos.job import JobCreate, JobResponse, JobType


routing_map = {"user": USER_OUTPUT_STREAM, "background": BACKGROUND_OUTPUT_STREAM}

publisher = RedisPublisherRouter(
	routing_key=["header","type"], routing_map=routing_map
)

def publish_job(job: JobResponse)->None:
	try:	
         
		# NEED TO REWRITE ALL MESSAGE PAYLOADS STRUCTURES!!!!!!
		payload = MessageURLPayload(url=job.article_url, source_rss="unkown")

		message = Message(
			header=MessageHeader(
				message_id=hashlib.md5(job.article_url.encode()).hexdigest(),
				timestamp=datetime.datetime.now().isoformat(),
				type=JobType.BACKGROUND,
			),
			data=payload,
		)
		message_as_dict = message.model_dump()
		publisher.publish_one(message_as_dict)

	except Exception as e:
		raise e
