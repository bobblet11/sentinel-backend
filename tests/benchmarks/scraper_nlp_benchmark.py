from typing import Any, Dict, List, Tuple

from pydantic import ValidationError

from common.models.api.redis_models import Message
from tests.benchmarks.benchmark_base import BenchmarkTemplate

URL_SPREAD = {
    "euronews": "https://www.euronews.com/2026/03/30/trump-threatens-to-obliterate-irans-kharg-island-oil-hub-if-no-deal-reached-shortly",
}

class WebScraperNLPBenchmark(BenchmarkTemplate):
    """
    Benchmark to see if author, published_date, news_outlet is filled out by the hardcoded parsers in WebScraper.
    Jobs created are simulated outputs from the ingestor, covering all news outlets in the RSS feed.
    """

    def __init__(self):
        # profiles should be JUST web scraper
        super().__init__(
            mode="redis",
            input_stream="background:to.be.scraped",
            output_stream="background:to.be.retrieval",
            failure_streams=["failure:to.be.scraped", "failure:to.be.nlp"],
        )

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
        """Validate that all fields in Message are non-None."""
        valid, invalid = [], []
        for job in successfully_processed_jobs:
            try:
                message = Message(**job["data"])
                # Check every field in header
                header_ok = all(
                    getattr(message.header, field_name) is not None
                    for field_name in message.header.model_fields.keys()
                )
                # Check every required field in payload
                payload_ok = all(
                    getattr(message.payload, field_name) is not None
                    for field_name in message.payload.model_fields.keys()
                    if field_name not in [
                        "sentences", "claims_in_article", "entities_in_article", "bias_profile",
                    ]
                )
                if header_ok and payload_ok:
                    valid.append(job)
                else:
                    invalid.append(job)
            except ValidationError as e:
                invalid.append({"job": job, "error": str(e)})
        return valid, invalid
if __name__ == "__main__":
    benchmark = WebScraperNLPBenchmark()
    results = benchmark.run()
