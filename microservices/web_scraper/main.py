import datetime

from common.io.redirect_and_modify import redirect_and_modify
from common.io.utils import indent_with_space
from microservices.web_scraper.ScraperService import ScraperService
import signal


def exec():
    scraper_service = ScraperService()
    
    signal.signal(signal.SIGINT, scraper_service.shutdown)
    signal.signal(signal.SIGTERM, scraper_service.shutdown)
    
    scraper_service.run()

if __name__ == "__main__":

    print(f"\n\nmain.py is being run. It is currently {datetime.datetime.now()}")
    exec()
    print(f"\n\nmain.py is finished. It is currently {datetime.datetime.now()}")
