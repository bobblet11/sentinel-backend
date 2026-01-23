import json
from datetime import datetime
import logging
import os

from common.redis_client.duplicate_filter_mock import RedisDuplicateFilterMock
os.environ['MAX_INGESTOR_WORKERS'] = '10'
os.environ['REDIS_DUPLICATE_FILTER_KEY'] = ''
os.environ['OUTPUT_STREAM'] = ''
from pathlib import Path
from typing import Dict, List
from dataclasses import asdict
from pydantic import TypeAdapter

from common.io.logging import setup_logging
from microservices.ingestor.main import RssSourceCategoryEntry, RssSourceEntry, categorise_rss_sources_by_payment_tier
from microservices.ingestor.rss_ingestor import Article, RssIngestor

ARTICLES_PATH = Path("tests/articles/articles.jsonl")
LOG_DIR_PATH = Path("tests/articles")

RSS_FEED_FILE_NAME:str = "rss_feeds.json"
PATH_TO_RSS_FEED_FILE: Path = Path("microservices/ingestor") / RSS_FEED_FILE_NAME


def fetch_sample_articles(rss_ingestor:RssIngestor, logger:logging.Logger):
	"""Generate realistic test articles."""
	raw_articles: List[Article] = list(rss_ingestor.fetch_articles())
	raw_articles: List[Dict[str, str]] = [asdict(x) for x in raw_articles]
	# Save as JSONL
	with open("tests/articles/articles.jsonl", "w") as f:
		for article in raw_articles:
			f.write(json.dumps(article) + "\n")

	logger.info(f"✅ Created {len(raw_articles)} test articles in tests/articles/articles.jsonl")

if __name__ == "__main__":
	ARTICLES_PATH.touch(mode=777, exist_ok=True)
	os.chmod(str(ARTICLES_PATH), 0o666)
	setup_logging(level=logging.DEBUG,container_name="benchmark_script", log_directory=LOG_DIR_PATH)
	main_logger: logging.Logger = logging.getLogger("__main__")
	

	try:
		adapter = TypeAdapter(List[RssSourceEntry])
		with open(PATH_TO_RSS_FEED_FILE, "rb") as rss_feed_file:
			rss_sources = adapter.validate_json(rss_feed_file.read())
	except FileNotFoundError:
		main_logger.error(f"No {RSS_FEED_FILE_NAME} file found at {PATH_TO_RSS_FEED_FILE.absolute()}")
		exit(1)	
	categorised_sources:Dict[str, RssSourceCategoryEntry] = categorise_rss_sources_by_payment_tier(rss_sources)
	all_rss_feeds:List[str] = []
	for entry in categorised_sources.values():
		all_rss_feeds.extend(entry.feed_urls)
	total_number_of_rss_feeds:int = len(all_rss_feeds)
	for tier, entry in categorised_sources.items():
		percentage_of_feeds = 100 * (entry.number_of_feeds / total_number_of_rss_feeds) if total_number_of_rss_feeds > 0 else 0
		all_rss_feeds.extend(entry.feed_urls)
		main_logger.info(
			f"Tier {tier:<10} | Sources: {entry.number_of_sources:<3} | "
			f"Feeds: {entry.number_of_feeds:<3} ({percentage_of_feeds:.1f}%)"
		)
	main_logger.info(f"Total consolidated feeds: {total_number_of_rss_feeds}")



	mock_duplicate_filter = RedisDuplicateFilterMock()
	mock_publisher = RedisDuplicateFilterMock()
	fetch_sample_articles(RssIngestor(all_rss_feeds,duplicate_filter=mock_duplicate_filter, publisher=mock_publisher), logger=main_logger)
