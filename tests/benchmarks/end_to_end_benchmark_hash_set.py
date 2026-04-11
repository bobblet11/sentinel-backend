import json
import time
from typing import Any, Dict, List, Tuple
from pydantic import ValidationError

from common.models.api.redis_models import Message
from tests.benchmarks.benchmark_base import BenchmarkResults, BenchmarkTemplate
from common.redis_client.hash_store import RedisHashStore

URL_SPREAD = []  # fill with test URLs


class EndToEndBenchmarkUser(BenchmarkTemplate):
    """
    Benchmark to validate full Message schema and measure latency across services.
    """

    def __init__(self, hash_key):
        super().__init__(
            mode="redis",
            input_stream="background:to.be.scraped",
            output_stream="",
            failure_streams=["failure:to.be.scraped", "failure:to.be.nlp", "failure:to.be.retrieval"],
        )
        self.hash_key = hash_key
        self.hash_store = RedisHashStore(hash_namespace=hash_key)

    def generate_jobs(self) -> List[Dict[str, Any]]:
        """Return a list of Redis jobs using URL_SPREAD."""
        jobs = []
        # Use the same URL_SPREAD as in the good benchmark
        i = 0
        for url in URL_SPREAD.values():
            if i < len(URL_SPREAD.values())/2:
                is_background = True
            else:
                is_background = False
                
            message = self._create_redis_job(url, is_background=is_background)
            jobs.append(message.model_dump())
        return jobs
    
    
    
    def _poll_results(
        self,
        expected_uids: List[str],
        timeout_s: float = 60.0,
        poll_interval: float = 0.5,
    ) -> Dict[str, Dict[str, Any]]:

        poll_count = 0
        expected = set(expected_uids)
        results: Dict[str, Dict[str, Any]] = {}
        streams:Dict[str,str] = {stream: ">" for stream in [self.output_stream] + self.failure_streams}
        start = time.time()

        while len(results) < len(expected) and (time.time() - start) < timeout_s:
            if poll_count >= self.MAX_POLL:
                raise Exception("Failed to complete test, some jobs are stuck")

            poll_count += 1


            for stream_name in [self.output_stream] + self.failure_streams:
                messages = self.redis.xrange(stream_name, min="-", max="+")
                is_failure = stream_name in self.failure_streams

                for redis_message_id, fields in messages:
                    try:

                        message_dict:Dict[str, Any] = self._decode_one_message(
                            stream_name, redis_message_id, fields
                        )
                        uid = message_dict.get("data", {}).get("header",{}).get("uid")
                        message_dict["is_failure"] = is_failure
                        if uid in expected:
                            results[uid] = message_dict

                    except json.JSONDecodeError as e:
                        self.logger.error(
                            f"Exception on message {redis_message_id}... Could not decode message from stream '{stream_name}' due to JSON decode error: {e}"
                        )
                        raise
            
            
            for uid in list(expected - results.keys()):
                payload = self.hash_store.get(uid)
                if payload:
                    results[uid] = {"uid": uid, "payload": payload}

            if len(results) < len(expected):
                time.sleep(poll_interval)

            
            time.sleep(poll_interval)

        return results

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

    def run(self) -> BenchmarkResults:
        self.setup()

        jobs = self.generate_jobs()
        print(f"Generated {len(jobs)} jobs")

        # Submit jobs
        start = time.time()
        submit_successes, submit_failures = self._submit_jobs_concurrently(jobs)
        elapsed_submission = time.time() - start

        print(f"Submitted {len(submit_successes)} jobs successfully, {len(submit_failures)} failed")

        # Extract UIDs
        expected_uids = [self._extract_uid(s) for s in submit_successes if self._extract_uid(s)]

        # Poll Redis for results
        print("Polling Redis for results...")
        results = self._poll_results(expected_uids)
  
        successfully_processed_jobs = [j for _, j in results.items() if not j.get("is_failure")]
        failure_processed_jobs = [j for _, j in results.items() if j.get("is_failure")]
        elapsed_completion = time.time() - start
        
        # Validate
        valid_jobs, invalid_jobs = self.validate_results(successfully_processed_jobs)
        
        return BenchmarkResults(
            time_elapsed_submission=elapsed_submission,
            time_elapsed_processing=elapsed_completion,
            jobs_submitted=len(jobs),
            submit_successes=len(submit_successes),
            submit_failures=len(submit_failures),
            mode=self.mode,
            successfully_processed_results = successfully_processed_jobs,
            failure_processed_results = failure_processed_jobs,
            valid_processed_results = valid_jobs,
            invalid_processed_results = invalid_jobs
        )
