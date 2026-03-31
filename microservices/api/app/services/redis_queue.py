import datetime
import hashlib
from common.models.api.dtos.job import JobStage, JobStatus
from common.models.api.redis_models import Message, MessageHeader, MessagePayload, MessageTimestamp, add_timestamp_to_message
from common.redis_client.consumer import RedisConsumer
from common.redis_client.publisher_router import RedisPublisherRouter
from microservices.api.app.core.config import OUTPUT_STREAM
from microservices.api.app.dtos.job import JobCreate, JobResponse, JobType
from microservices.api.app.models.article import Article
from microservices.api.app.models.job import Job
from typing import Optional
import re

OUTLET_PATTERNS = {
    r"(bbc\.com|bbc\.co\.uk|www\.bbc\.com)": "BBC",
    r"(theguardian\.com|www\.theguardian\.com)": "The Guardian",
    r"(cbc\.ca|www\.cbc\.ca)": "CBC",
    r"(euronews\.com|www\.euronews\.com)": "Euronews",
    r"(abcnews\.go\.com|abcnews\.com)": "ABC",
    r"(cbsnews\.com|www\.cbsnews\.com)": "CBS",
    r"(nbcnews\.com|www\.nbcnews\.com)": "NBC",
    r"(npr\.org|www\.npr\.org)": "NPR",
    r"(foxnews\.com|www\.foxnews\.com)": "Fox News",
    r"(reuters\.com|www\.reuters\.com)": "Reuters",
    r"(apnews\.com|www\.apnews\.com)": "AP News",
    r"(aljazeera\.com|www\.aljazeera\.com)": "Al Jazeera",
}

def match_outlet_name(article_url: str) -> Optional[str]:
    for pattern, outlet in OUTLET_PATTERNS.items():
        if re.search(pattern, article_url):
            return outlet
    return None

routing_map = {JobType.USER.value: OUTPUT_STREAM, JobType.BACKGROUND.value: OUTPUT_STREAM}

publisher = RedisPublisherRouter(
	routing_key=["header","type"], routing_map=routing_map
)

def publish_job(job: Job, article: Article, job_dto: JobCreate)->None:
	try:	
         
		# payload = MessagePayload(article_url=article.url, raw_html=job_dto.article_html, parsed_text=job_dto.article_text, news_outlet=job_dto.news_outlet, title=job_dto.article_title, summary=job_dto.article_summary)
		matched_outlet = match_outlet_name(article.url or "")
		news_outlet = matched_outlet or job_dto.news_outlet

		payload = MessagePayload(article_url=article.url, raw_html=job_dto.article_html, parsed_text=job_dto.article_text, news_outlet=news_outlet, title=job_dto.article_title, summary=job_dto.article_summary)
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

  
		message_as_dict = message.model_dump()
		publisher.publish_one(message_as_dict)

	except Exception as e:
         
		print(e)
		raise e
