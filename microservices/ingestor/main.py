import logging
import sys
import traceback 
from pydantic import TypeAdapter
from typing import Dict, List
from pathlib import Path
from microservices.ingestor.rss_ingestor import RssIngestor
from common.io.logging import TimeDeltaConfig, setup_logging
from dataclasses import field 
from dataclasses import dataclass
from enum import StrEnum

SERVICE_NAME:str = "ingestor"
RSS_FEED_FILE_NAME:str = "rss_feeds.json"
PATH_TO_RSS_FEED_FILE: Path = Path(__file__).resolve().parent / RSS_FEED_FILE_NAME
class PaymentTier(StrEnum):
    FREE = "FREE"
    METERED = "METERED"
    PAYWALLED = "PAYWALLED"
@dataclass(frozen=True)
class RssSourceEntry:
    name: str
    payment_tier: PaymentTier 
    feeds: List[str]
    
@dataclass
class RssSourceCategoryEntry:
    number_of_feeds: int = 0
    number_of_sources: int = 0
    feed_urls: List[str]  = field(default_factory=list)


def categorise_rss_sources_by_payment_tier(sources:List[RssSourceEntry]) -> Dict[PaymentTier,RssSourceCategoryEntry]:
    categories: Dict[PaymentTier, RssSourceCategoryEntry] = {
        tier: RssSourceCategoryEntry() for tier in PaymentTier
    }
    for source in sources:
        category = categories[source.payment_tier]
        category.number_of_sources += 1
        category.number_of_feeds += len(source.feeds)
        category.feed_urls.extend(source.feeds)
        
    return categories



if __name__ == "__main__":
    try:
        
        setup_logging(execution_mode="cron", max_age_of_log_file=TimeDeltaConfig(days=3), level=logging.DEBUG,container_name=SERVICE_NAME)
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

        rss_ingestor = RssIngestor(all_rss_feeds)
        rss_ingestor.run()
    except Exception as e:
        print(f"CRITICAL: Application failed to start: {e}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)
