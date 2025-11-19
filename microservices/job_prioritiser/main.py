import datetime
import signal

from microservices.job_prioritiser.PrioritiserService import PrioritiserService


def exec():
    """
    Main execution loop. Fetches a batch of messages, prioritizes them,
    and then processes them one by one.
    """

    prioritiser = PrioritiserService()

    # Register signal handlers for graceful shutdown (Ctrl+C)
    signal.signal(signal.SIGINT, prioritiser.shutdown)
    signal.signal(signal.SIGTERM, prioritiser.shutdown)

    prioritiser.run()


if __name__ == "__main__":
    print(f"\n\nmain.py is being run. It is currently {datetime.datetime.now()}")
    exec()
    print(f"\n\nmain.py is finished. It is currently {datetime.datetime.now()}")
