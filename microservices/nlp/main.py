from logging import Logger, getLogger, DEBUG
import signal
from common.io.logging import setup_logging
from microservices.nlp.nlp_service import SentinelNLP

if __name__ == "__main__":
    setup_logging(level=DEBUG, container_name="nlp")
    main_logger: Logger = getLogger("__main__")

    nlp_service = SentinelNLP()
    signal.signal(signal.SIGINT, nlp_service.shutdown)
    signal.signal(signal.SIGTERM, nlp_service.shutdown)
    nlp_service.run()
