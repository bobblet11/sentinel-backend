import signal
from logging import Logger, getLogger, DEBUG
from common.io.logging import setup_logging
from microservices.job_prioritiser.prioritiser_service import PrioritiserService
from microservices.job_prioritiser.config import CONSUMER_NAME

if __name__ == "__main__":
    setup_logging(level=DEBUG, container_name=CONSUMER_NAME)
    main_logger: Logger = getLogger("__main__")
    
    prioritiser = PrioritiserService()

    signal.signal(signal.SIGINT, prioritiser.shutdown)
    signal.signal(signal.SIGTERM, prioritiser.shutdown)

    prioritiser.run()
