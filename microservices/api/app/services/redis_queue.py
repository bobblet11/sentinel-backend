import datetime
from typing import Any, Optional, cast

from common.models.api.dtos.job import JobStage, JobStatus
from common.models.api.redis_models import (Message, MessageHeader,
                                            MessagePayload,
                                            add_timestamp_to_message)
from common.redis_client.publisher import RedisPublisher
from common.redis_client.publisher_router import RedisPublisherRouter
from microservices.api.app.core.config import OUTPUT_STREAM
from microservices.api.app.dtos.job import JobCreate, JobType
from microservices.api.app.models.article import Article
from microservices.api.app.models.job import Job

routing_map = RedisPublisherRouter.generate_router_mapping([OUTPUT_STREAM,"background:to.be.scraped"], [JobType.USER.value, JobType.BACKGROUND.value])
publisher_router = RedisPublisherRouter(
	routing_key=["header","type"], routing_map=routing_map
)
direct_user_nlp_publisher = RedisPublisher("user:to.be.nlp")


def _should_bypass_scraper(job_type: str, payload: MessagePayload) -> bool:
	return (
		job_type == JobType.USER.value
		and bool(payload.raw_html)
		and bool(payload.parsed_text)
	)


def publish_job(job: Job, article: Article, job_dto: JobCreate)->None:
	try:	
		article_url = cast(str, article.url)
		article_html = job_dto.article_html or cast(Optional[str], article.html)
		article_text = job_dto.article_text or cast(Optional[str], article.text)
		article_title = job_dto.article_title or cast(Optional[str], article.title)
		article_published_at = cast(Any, article.publishedAt)
		job_id = cast(Optional[int], job.id)
		job_type = cast(str, job.type)

		payload = MessagePayload(
			article_url=article_url,
			raw_html=article_html,
			parsed_text=article_text,
			news_outlet=job_dto.news_outlet or (article.outlet.name if article.outlet else None),
			title=article_title,
			author=job_dto.article_author,
			publish_date=job_dto.article_published_at or (article_published_at.isoformat() if article_published_at else None),
			summary=job_dto.article_summary,
		)
		message = Message(
			header=MessageHeader(
				id=job_id,
                    		uid=str(job.uid),
				created_at=datetime.datetime.now().isoformat(),
				status=JobStatus.PENDING,
				type=job_type,
			),
			payload=payload,
			stage_timestamps=[]
		)
  
		message = add_timestamp_to_message(message=message, stage_name=JobStage.INGESTED)

  
		message_payload = message.model_dump(mode='json')
		if _should_bypass_scraper(job_type, payload):
			direct_user_nlp_publisher.publish_one(message_payload)
		else:
			publisher_router.publish_one(message_payload)

	except Exception as e:
         
		print(e)
		raise e
