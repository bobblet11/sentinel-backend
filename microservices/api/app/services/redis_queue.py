import datetime
import hashlib
import json
from common.models.api.dtos.job import JobStage, JobStatus
from common.models.api.redis_models import Message, MessageHeader, MessagePayload, MessageTimestamp, add_timestamp_to_message
from common.redis_client.consumer import RedisConsumer
from common.redis_client.publisher_router import RedisPublisherRouter
from microservices.api.app.core.config import OUTPUT_STREAM
from microservices.api.app.dtos.job import JobCreate, JobResponse, JobType
from microservices.api.app.models.article import Article
from microservices.api.app.models.job import Job
from typing import Optional



routing_map = RedisPublisherRouter.generate_router_mapping([OUTPUT_STREAM,"background:to.be.scraped"], [JobType.USER.value, JobType.BACKGROUND.value])
publisher_router = RedisPublisherRouter(
	routing_key=["header","type"], routing_map=routing_map
)


def publish_job(job: Job, article: Article, job_dto: JobCreate)->None:
	try:	
		payload = MessagePayload(
			article_url=article.url,
			raw_html=job_dto.article_html or article.html,
			parsed_text=job_dto.article_text or article.text,
			news_outlet=job_dto.news_outlet or (article.outlet.name if article.outlet else None),
			title=job_dto.article_title or article.title,
			publish_date=job_dto.article_published_at or (article.publishedAt.isoformat() if article.publishedAt else None),
			summary=job_dto.article_summary,
		)
		message = Message(
			header=MessageHeader(
				id=job.id,
                    		uid=str(job.uid),
				created_at=datetime.datetime.now().isoformat(),
				status=JobStatus.PENDING,
				type=job.type,
			),
			payload=payload,
			stage_timestamps=[]
		)
  
		message = add_timestamp_to_message(message=message, stage_name=JobStage.INGESTED)

  
		message_payload = message.model_dump(mode='json')
		publisher_router.publish_one(message_payload)

	except Exception as e:
         
		print(e)
		raise e
