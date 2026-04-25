from typing import Any, Dict, List, Tuple

from pydantic import ValidationError

from common.models.api.redis_models import Message
from tests.benchmarks.benchmark_base import BenchmarkTemplate

URL_SPREAD = {
    "bbc": "https://www.bbc.com/news/articles/c937gd1vq7xo",
    "abc": "https://abcnews.com/Politics/senate-passes-bill-fund-dhs-except-ice-parts/story?id=131461819",
    "cbc": "https://www.cbc.ca/news/world/iran-strikes-military-base-us-troops-wounded-9.7145616",
    "cbs": "https://www.cbsnews.com/news/michael-jordan-nascar-lawsuit-vision-for-sport-gayle-king-interview/",
    "npr": "https://www.npr.org/2026/03/26/nx-s1-5762974/education-department-building",
    "nbc": "https://www.nbcnews.com/politics/trump-administration/trump-johnson-dhs-house-rebels-senate-bill-ice-cbp-rcna265507",
    "euronews": "https://www.euronews.com/2026/03/30/trump-threatens-to-obliterate-irans-kharg-island-oil-hub-if-no-deal-reached-shortly",
    "guardian": "https://www.theguardian.com/world/2026/mar/30/egypt-pakistan-saudi-arabia-turkey-talks-embryo-new-order",
}


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

    # def setup(self):
    #     """Prepare environment, clear Redis, warm caches, etc."""
    #     for stream in [self.input_stream, self.output_stream] + self.failure_streams:
    #         self.redis.xtrim(stream, maxlen=0)
    #     print("[INFO] Redis streams cleared")

    def generate_jobs(self) -> List[Dict[str, Any]]:
        """Return a list of Redis jobs using URL_SPREAD."""
        jobs = []
        # Use the same URL_SPREAD as in the good benchmark
        for url in URL_SPREAD.values():
            message = self._create_redis_job(url)
            jobs.append(message.model_dump())
        return jobs

    def validate_results(
        self, successfully_processed_jobs: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Validation logic lifted from the good benchmark, but:
        - Only checks:
            - news_outlet in allowed_outlets,
            - publish_date,
            - and author (non-None).
        """
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
                    valid.append(job)
                else:
                    invalid.append(job)
            except ValidationError as e:
                invalid.append({"job": job, "error": str(e)})

        return valid, invalid


if __name__ == "__main__":
    benchmark = WebScraperBenchmark()
    results = benchmark.run()
