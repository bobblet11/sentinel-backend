import signal

from microservices.web_scraper.ScraperService import ScraperService

if __name__ == "__main__":
    scraper_service = ScraperService()
    signal.signal(signal.SIGINT, scraper_service.shutdown)
    signal.signal(signal.SIGTERM, scraper_service.shutdown)
    scraper_service.run()
