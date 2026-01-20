import datetime
import hashlib
from common.models.api.dtos.job import JobStatus
from common.models.api.redis_models import Message, MessageHeader, MessagePayload
from common.redis_client.consumer import RedisConsumer
from common.redis_client.publisher_router import RedisPublisherRouter
from microservices.api.app.core.config import OUTPUT_STREAM
from microservices.api.app.dtos.job import JobCreate, JobResponse, JobType
from microservices.api.app.models.article import Article
from microservices.api.app.models.job import Job


routing_map = {"user": OUTPUT_STREAM, "background": OUTPUT_STREAM}

publisher = RedisPublisherRouter(
	routing_key=["header","type"], routing_map=routing_map
)

def publish_job(job: Job, article: Article, job_dto: JobCreate)->None:
	try:	
         
		payload = MessagePayload(article_url=article.url, news_outlet=job_dto.news_outlet, title=job_dto.title, summary=job_dto.summary)
		
		message = Message(
			header=MessageHeader(
				id=job.id,
                    		uid=job.uid,
				created_at=datetime.datetime.now().isoformat(),
				status=JobStatus.PENDING,
				type=JobType.USER,
			),
			data=payload,
			stage_timestamps=[]
		)
  
		message_as_dict = message.model_dump()
		publisher.publish_one(message_as_dict)

	except Exception as e:
		raise e
