from typing import Any, Dict, List, Tuple

from pydantic import ValidationError

from common.models.api.redis_models import Message
from common.models.api.validation_helpers import (
    validate_after_ingestor,
    validate_after_nlp,
    validate_after_retrieval,
    validate_after_webscraper,
)
from tests.benchmarks.benchmark_base import BenchmarkTemplate

URL_SPREAD_BACKGROUND = {}

URL_SPREAD_USER = {
    "bbc": "https://www.bbc.com/news/articles/cn0wzxqyx17o",
    "abc": "https://abcnews.com/International/live-updates/iran-live-updates-us-blockade-irans-strait-hormuz/?id=131983647",
    "cbc": "https://www.cbc.ca/news/health/canadian-cancer-projections-9.7159535",
    "cbs": "https://www.cbsnews.com/live-updates/iran-war-us-iran-ports-blockade-strait-of-hormuz-trump/",
    "npr": "https://www.npr.org/2026/04/13/nx-s1-5777582/many-private-colleges-at-risk-of-closing",
    "nbc": "https://www.nbcnews.com/business/markets/oil-prices-surge-trump-says-us-will-blockade-strait-hormuz-rcna330824",
    "euronews": "https://www.euronews.com/my-europe/2026/04/13/magyar-victory-will-bring-more-european-unity-former-european-council-chief-michel-says",
    "guardian": "https://www.theguardian.com/business/2026/apr/13/oil-price-tops-100-dollars-barrel-us-blockade-strait-of-hormuz",
}


class EndToEndUser(BenchmarkTemplate):
    """
    Benchmark to validate full Message schema and measure latency across services.
    """

    def __init__(self):
        super().__init__(
            input_stream="background:to.be.scraped",
            output_stream="all:benchmark.output",
            failure_streams=[
                "failure:to.be.scraped",
                "failure:to.be.nlp",
                "failure:to.be.retrieval",
            ],
        )

    def generate_jobs(self) -> List[Dict[str, Any]]:
        """Return a list of Redis jobs using URL_SPREAD."""
        jobs = []
        # Use the same URL_SPREAD as in the good benchmark
        for url in URL_SPREAD_BACKGROUND.values():
            message = self._create_redis_job(url, is_background=True)
            jobs.append({"submission_type": "redis", "payload": message})

        for url in URL_SPREAD_USER.values():
            request = self._create_api_job(url, is_background=False)
            jobs.append({"submission_type": "api", "payload": request})
        return jobs

    def validate_results(
        self, successfully_processed_jobs: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        valid, invalid = [], []

        for job in successfully_processed_jobs:
            try:
                # Wrap into Message for schema validation
                message = Message(**job["data"])

                # Run stage‑specific validators
                try:
                    validate_after_ingestor(message=message)
                    validate_after_webscraper(stream_message=None, message=message)
                    validate_after_nlp(stream_message=None, message=message)
                    validate_after_retrieval(stream_message=None, message=message)
                except ValueError as ve:
                    # Stage validation failed
                    invalid.append({"job": job, "error": str(ve)})
                    continue

                # If all validators pass, mark as valid
                valid.append(job)

            except ValidationError as e:
                invalid.append({"job": job, "error": str(e)})

        return valid, invalid


if __name__ == "__main__":
    benchmark = EndToEndUser()
    benchmark.run()
