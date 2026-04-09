import time
from typing import Any, Dict, List, Tuple

from pydantic import ValidationError

from common.models.api.redis_models import Message
from tests.benchmarks.benchmark_base import BenchmarkResults, BenchmarkTemplate


URL_SPREAD_1 = []
URL_SPREAD_2 = []


class WebScraperBenchmark(BenchmarkTemplate):
    """
    Benchmark to see if author, published_date, news_outlet is filled out by the hardcoded parsers in WebScraper.
    Jobs created are simulated outputs from the ingestor, covering all news outlets in the RSS feed.
    """

    def __init__(self):
        # profiles should be JUST web scraper
        super().__init__(
            mode="redis",
            input_stream="background:to.be.scraped",
            output_stream="background:to.be.nlp",
            failure_streams=["failure:to.be.scraped"],
        )

    def setup(self):
        """Prepare environment, clear Redis, warm caches, etc."""
        for stream in [self.input_stream, self.output_stream] + self.failure_streams:
            self.redis.xtrim(stream, maxlen=0)
        print("[INFO] Redis streams cleared")

    def generate_jobs(self) -> List[Dict[str, Any]]:
        """Return a list of Redis jobs using URL spreads."""
        jobs = []
        for url in URL_SPREAD_1 + URL_SPREAD_2:
            # outlet = self.match_outlet_name(url)
            message = self._create_redis_job(url)
            jobs.append(message.__dict__)
        return jobs

    def validate_results(self, successfully_processed_jobs):
        valid, invalid = [], []
        allowed_outlets = set(self.OUTLET_PATTERNS.values())

        for job in successfully_processed_jobs:
            try:
                # Parse into a Message model
                message = Message(**job["data"])
                
                # Check outlet and required fields
                if (
                    message.payload.news_outlet in allowed_outlets
                    and message.payload.publish_date
                    and message.payload.author
                ):
                    print("Message is valid")
                    print(f"News Outlet: {message.payload.news_outlet}")
                    print(f"Publish Date: {message.payload.publish_date}")
                    print(f"Author: {message.payload.author}")
                    valid.append(job)
                else:
                    invalid.append(job)
            except ValidationError as e:
                invalid.append({"job": job, "error": str(e)})

        return valid, 


if __name__ == "__main__":
    benchmark = WebScraperBenchmark()
    results = benchmark.run()
    results.print_report()
