import logging
import signal
from common.io.logging import setup_logging
from microservices.web_scraper.scraper_service import ScraperService
from logging import Logger, getLogger, DEBUG
CONTAINER_NAME="web_scraper"

if __name__ == "__main__":
    setup_logging(level=DEBUG,container_name=CONTAINER_NAME)

    scraper_service = ScraperService()
    signal.signal(signal.SIGINT, scraper_service.shutdown)
    signal.signal(signal.SIGTERM, scraper_service.shutdown)
    scraper_service.run()
