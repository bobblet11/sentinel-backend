import datetime
import hashlib
import json
import time
import random
import redis
import requests
import re
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Tuple, Optional
from abc import ABC, abstractmethod

from common.models.api.dtos.job import JobStatus, JobType
from common.models.api.redis_models import Message, MessageHeader, MessagePayload


@dataclass
class BenchmarkResults:
    time_elapsed_submission: float
    time_elapsed_processing: float
    jobs_submitted: int
    submit_successes: int
    submit_failures: int
    mode: str
    failure_processed_results: List[Dict[str,Any]]
    successfully_processed_results: List[Dict[str, Any]]
    valid_processed_results: List[Dict[str, Any]]
    invalid_processed_results: List[Dict[str, Any]]

    def get_report(self) -> str:
        return (
            f"Mode: {self.mode}\n"
            f"Jobs submitted: {self.jobs_submitted}\n"
            f"Submit successes: {self.submit_successes}\n"
            f"Submit failures: {self.submit_failures}\n"
            f"Valid results: {len(self.valid_processed_results)}\n"
            f"Invalid results: {len(self.invalid_processed_results)}\n"
            f"Failures processed: {len(self.failure_processed_results)}\n"
            f"Total latency: {self.total_time_elapsed:.2f}s"
        )

    def print_report(self) -> None:
        print(self.get_report())

class BenchmarkTemplate(ABC):
    """
    A reusable benchmark framework that can:
    - Submit jobs via API or directly into Redis
    - Poll Redis streams for results
    - Measure end-to-end latency
    - Validate correctness
    """

    # Default configuration
    API_URL = "http://localhost:8001/api/v1/jobs"
    REDIS_HOST = "redis"
    REDIS_PORT = 6379
    
    MAX_POLL = 1_000
    INPUT_STREAM = "background:to.be.scraped"
    OUTPUT_STREAM = "background:to.be.nlp"
    FAILURE_STREAMS = ["failure:to.be.scraped", "failure:to.be.nlp"]
    OUTLET_PATTERNS = {
    r"(bbc\.com|bbc\.co\.uk|www\.bbc\.com)": "BBC",
    r"(theguardian\.com|www\.theguardian\.com)": "The Guardian",
    r"(cbc\.ca|www\.cbc\.ca)": "CBC",
    r"(euronews\.com|www\.euronews\.com)": "Euronews",
    r"(abcnews\.go\.com|abcnews\.com)": "ABC",
    r"(cbsnews\.com|www\.cbsnews\.com)": "CBS",
    r"(nbcnews\.com|www\.nbcnews\.com)": "NBC",
    r"(npr\.org|www\.npr\.org)": "NPR",
    r"(foxnews\.com|www\.foxnews\.com)": "Fox News",
    r"(reuters\.com|www\.reuters\.com)": "Reuters",
    r"(apnews\.com|www\.apnews\.com)": "AP News",
    r"(aljazeera\.com|www\.aljazeera\.com)": "Al Jazeera",
    }
    
    def __init__(self, input_stream:str, output_stream:str, failure_streams: List[str], mode: str = "api", max_workers: int = 20):
        assert mode in ("api", "redis")
        self.mode = mode
        self.max_workers = max_workers
        self.input_stream = input_stream
        self.output_stream = output_stream
        self.failure_streams = failure_streams
        print(f"--- Running {self.__class__.__name__} ---")
        print(f"Mode: {self.mode}")

        self.session = requests.Session()
        self.redis = redis.Redis(host=self.REDIS_HOST, port=self.REDIS_PORT, decode_responses=True)
        self.redis.ping() 
        print(f"[INFO] Connected to Redis on port {self.REDIS_PORT}")
 
    # ----------------------------------------------------------------------
    # ABSTRACT HOOKS
    # ----------------------------------------------------------------------
    @abstractmethod
    def setup(self):
        """Prepare environment, clear Redis, warm caches, etc."""
        pass

    @abstractmethod
    def generate_jobs(self) -> List[Dict[str, Any]]:
        """Return a list of job dicts: { 'article_url': ..., 'is_background': ... }"""
        pass

    @abstractmethod
    def validate_results(self, successfully_processed_jobs: List[Dict[str, Any]]) -> Tuple[List[Dict[str,Any]], List[Dict[str, Any]]]:
        """validate correctness of results."""
        # return successfully_processed_jobs, [] to skip
        pass

    # ----------------------------------------------------------------------
    # JOB SUBMISSION
    # ----------------------------------------------------------------------
    def match_outlet_name(self, article_url: str) -> Optional[str]:
        for pattern, outlet in self.OUTLET_PATTERNS.items():
            if re.search(pattern, article_url):
                return outlet
        return None    
    
    #job_create
    def _create_api_job(self, article_url:str, is_background: bool = True) -> Dict[str, Any]:
        if not article_url:
            raise Exception("article url missing, minumum data required is a article url")    
        return {
                "article_url" : article_url,
                "is_background" : is_background
        }

    #payload
    def _create_redis_job(self, article_url:str, news_outlet:str = None) -> Message:

        if not article_url:
            raise Exception("article url missing, minumum data required is a article url")

        payload = MessagePayload(article_url=article_url, news_outlet=news_outlet, title=None, summary=None)
        job_uid = hashlib.md5(article_url.encode()).hexdigest()[:36]
        message = Message(
            header=MessageHeader(
                id=None,
                uid=job_uid,
                created_at=datetime.now().isoformat(),
                status=JobStatus.PENDING.value,
                type=JobType.BACKGROUND.value,
            ),
            payload=payload,
            stage_timestamps=[]
        )
        return message
        

    def _submit_job_api(self, job_create: Dict[str, Any]) -> Dict[str, Any]:
        try:
            resp = self.session.post(self.API_URL, json=job_create, timeout=10)
            resp.raise_for_status()
            return {"job_create" : job_create, "response" : resp.json()}
        except Exception as e:
            return {"error": str(e), "job_create": job_create}

    def _submit_job_redis(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            payload_str = json.dumps(payload)
            redis_id = self.redis.xadd(self.input_stream, {"payload": payload_str}, approximate=True)
            return {"redis_id": redis_id, "payload": payload}
        except Exception as e:
            return {"error": str(e), "payload": payload}

    def _submit_jobs_concurrently(self, jobs: List[Dict[str, Any]]) -> Tuple[List[Any], List[Any]]:
        submit_fn = self._submit_job_api if self.mode == "api" else self._submit_job_redis
        # jobs created using the _create_... function
        successes, failures = [], []

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(submit_fn, job): job for job in jobs}

            for i, future in enumerate(as_completed(futures)):
                try:
                    result = future.result()
                    if "error" in result:
                        failures.append(result)
                    else:
                        successes.append(result)
                except Exception as e:
                    failures.append({"error": str(e), "job": futures[future]})

                print(f"Progress: {i+1}/{len(jobs)}", end="\r")

        return successes, failures

    # ----------------------------------------------------------------------
    # RESULT COLLECTION
    # ----------------------------------------------------------------------
    def _extract_uid(self, submission_result: Dict[str, Any]) -> Optional[str]:
        """
        Extract UID from API or Redis submission result.
        """
        if self.mode == "api":
            return submission_result.get("uid")

        # Redis mode: UID must be inside the job payload
        job = submission_result.get("payload", {})
        return job.get("header", {}).get("uid")

    def _decode_one_message(self, stream_name:str, redis_message_id:str, fields:Dict[str, Any]) -> Dict[str, Any]:
        """
        Decodes a single raw message from Redis, handling byte conversion and JSON parsing.
        """
        decoded_fields: Dict[str, Any] = fields
        message_data:Dict[str, Any] = {}

        if "payload" in decoded_fields:
            message_data = json.loads(decoded_fields["payload"])
        else:
            self.logger.warning(f"Message {redis_message_id} is missing 'payload' field.")
            message_data = decoded_fields

        return {
            "stream": stream_name,
            "redis_message_id": redis_message_id,
            "data": message_data,
        }

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

            time.sleep(poll_interval)

        return results

    # ----------------------------------------------------------------------
    # MAIN RUNNER
    # ----------------------------------------------------------------------
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
