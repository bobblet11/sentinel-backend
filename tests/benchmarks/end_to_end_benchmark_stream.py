import time
from typing import Any, Dict, List, Tuple
from pydantic import ValidationError

from common.models.api.redis_models import Message
from tests.benchmarks.benchmark_base import BenchmarkResults, BenchmarkTemplate


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

class EndToEndBenchmarkBackground(BenchmarkTemplate):
    """
    Benchmark to validate full Message schema and measure latency across services.
    """

    def __init__(self):
        super().__init__(
            mode="redis",
            input_stream="background:to.be.scraped",
            output_stream="background:to.be.retrieval",
            failure_streams=["failure:to.be.scraped", "failure:to.be.nlp", "failure:to.be.retrieval"],
        )

    def setup(self):
        """Clear Redis streams before running."""
        for stream in [self.input_stream, self.output_stream] + self.failure_streams:
            self.redis.xtrim(stream, maxlen=0)
        print("[INFO] Redis streams cleared")

    def generate_jobs(self) -> List[Dict[str, Any]]:
        """Generate Redis jobs from URL spread."""
        jobs = []
        i = 0
        for url in URL_SPREAD.values():
            if i < len(URL_SPREAD) / 2:
                background = True
            else:
                background = False
                
            message = self._create_redis_job(url, is_background=background)
            jobs.append(message.__dict__)
            i+=1
        return jobs

    def validate_results(
        self, successfully_processed_jobs: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Validate that all fields in Message are non-None."""
        valid, invalid = [], []
        for job in successfully_processed_jobs:
            try:
                message = Message(**job["data"])
                # Check every field in header and payload
                header_ok = all(getattr(message.header, f.name) is not None for f in message.header.__fields__.values())
                payload_ok = all(
                    getattr(message.payload, f.name) is not None
                    for f in message.payload.__fields__.values()
                    if f.name not in ["sentences", "claims_in_article", "entities_in_article", "bias_profile",
                                      "save_data_result", "save_job_result", "matches", "related_articles"]
                )
                if header_ok and payload_ok:
                    valid.append(job)
                else:
                    invalid.append(job)
            except ValidationError as e:
                invalid.append({"job": job, "error": str(e)})
        return valid, invalid


if __name__ == "__main__":
    benchmark = EndToEndBenchmarkBackground()
    benchmark.run()

