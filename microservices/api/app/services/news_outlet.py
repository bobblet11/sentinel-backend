from typing import Optional
import re
from microservices.api.app.dtos.job import JobCreate, JobResponse, JobType

OUTLET_PATTERNS = {
    r"(bbc\.com|bbc\.co\.uk|www\.bbc\.com)": "BBC",
    r"(theguardian\.com|www\.theguardian\.com)": "The Guardian",
    r"(cbc\.ca|www\.cbc\.ca)": "CBC",
    r"(euronews\.com|www\.euronews\.com)": "Euronews",
    r"(abcnews\.go\.com|abcnews\.com)": "ABC",
    r"(cbsnews\.com|www\.cbsnews\.com)": "CBS",
    r"(nbcnews\.com|www\.nbcnews\.com|feeds\.nbcnews\.com)": "NBC",
    r"(npr\.org|www\.npr\.org)": "NPR",
    r"(foxnews\.com|www\.foxnews\.com)": "Fox News",
    r"(reuters\.com|www\.reuters\.com)": "Reuters",
    r"(apnews\.com|www\.apnews\.com)": "AP News",
    r"(aljazeera\.com|www\.aljazeera\.com)": "Al Jazeera",
}

def match_outlet_name(article_url: str) -> Optional[str]:
    for pattern, outlet in OUTLET_PATTERNS.items():
        if re.search(pattern, article_url.lower().strip()):
            return outlet
    return None


def get_news_outlet(job_dto: JobCreate) -> Optional[str]:
	# payload = MessagePayload(article_url=article.url, raw_html=job_dto.article_html, parsed_text=job_dto.article_text, news_outlet=job_dto.news_outlet, title=job_dto.article_title, summary=job_dto.article_summary)
	matched_outlet = match_outlet_name(job_dto.article_url or "")
	news_outlet = matched_outlet or job_dto.news_outlet or None
	return news_outlet
