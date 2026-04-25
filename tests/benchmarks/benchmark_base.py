import hashlib
import json
import re
import time
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import redis
import requests

from common.models.api.dtos.job import JobStage, JobStatus, JobType
from common.models.api.redis_models import (Message, MessageHeader,
                                            MessagePayload)

# Define service boundaries (START/END pairs)
SERVICE_BOUNDARIES = {
    "WEB_SCRAPE": (JobStage.WEB_SCRAPE_START, JobStage.WEB_SCRAPE_END),
    "NLP": (JobStage.NLP_START, JobStage.NLP_END),
    "RETRIEVAL": (JobStage.RETRIEVAL_START, JobStage.RETRIEVAL_END)
}

# Define IN/OUT subtask pairs within services
SUBTASK_PAIRS = {
    # NLP subtasks
    "NLP.PREPROCESS": (JobStage.PREPROCESS_IN, JobStage.PREPROCESS_OUT),
    "NLP.NER": (JobStage.NER_IN, JobStage.NER_OUT),
    "NLP.SENT_EXTRACTION": (JobStage.SENT_EXTRACTION_IN, JobStage.SENT_EXTRACTION_OUT),
    "NLP.DECONTEXT": (JobStage.DECONTEXT_IN, JobStage.DECONTEXT_OUT),
    "NLP.CHECK_WORTHY": (JobStage.CHECK_WORTHY_IN, JobStage.CHECK_WORTHY_OUT),
    "NLP.ENTITY_MAPPING": (JobStage.CHECK_WORTHY_ENTITY_MAPPING_IN, JobStage.CHECK_WORTHY_ENTITY_MAPPING_OUT),
    "NLP.SENTENCE_EMBED": (JobStage.SENTENCE_EMBED_IN, JobStage.SENTENCE_EMBED_OUT),
    "NLP.CONVERT_TO_CLAIM": (JobStage.CONVERT_TO_CLAIM_IN, JobStage.CONVERT_TO_CLAIM_OUT),
    "NLP.BIAS_ANAL": (JobStage.BIAS_ANAL_IN, JobStage.BIAS_ANAL_OUT),
    
    # Web scrape subtasks  
    "WEB_SCRAPE.FETCH": (JobStage.FETCHED_IN, JobStage.FETCHED_OUT),
    "WEB_SCRAPE.PARSE": (JobStage.PARSED_IN, JobStage.PARSED_OUT),
    
    # Retrieval subtasks
    "RETRIEVAL.SAVE_DATA": (JobStage.SAVE_DATA_IN, JobStage.SAVE_DATA_OUT),
    "RETRIEVAL.RETRIEVE_EVIDENCE": (JobStage.RETRIEVE_EVIDENCE_IN, JobStage.RETRIEVE_EVIDENCE_OUT),
    "RETRIEVAL.UPDATE_JOB": (JobStage.UPDATE_JOB_IN, JobStage.UPDATE_JOB_OUT),
}

@dataclass
class MetricStats:
    """Stores detailed statistics for a single metric."""
    avg: float = 0.0
    p50: float = 0.0
    p75: float = 0.0
    p95: float = 0.0
    p50_job: Dict[str, Any] = None
    p75_job: Dict[str, Any] = None
    p95_job: Dict[str, Any] = None

@dataclass
class GroupStats:
    """Statistics for a single job type (ALL/USER/BACKGROUND)."""
    name: str
    job_count: int = 0
    service_latencies: Dict[str, MetricStats] = field(default_factory=dict)  # NEW: Service-level
    subtask_latencies: Dict[str, MetricStats] = field(default_factory=dict)  # NEW: Subtask-level  
    end_to_end: MetricStats = field(default_factory=MetricStats)
    raw_durations: Dict[str, List[float]] = field(default_factory=dict)

@dataclass
class BenchmarkResults:
    time_elapsed_submission: float
    time_elapsed_processing: float
    jobs_submitted: int
    submit_successes: int
    submit_failures: int
    failure_processed_results: List[Dict[str,Any]]
    successfully_processed_results: List[Dict[str, Any]]
    valid_processed_results: List[Dict[str, Any]]
    invalid_processed_results: List[Dict[str, Any]]

    def _get_metric_stats(self, values: List[float], jobs: List[Dict[str, Any]]) -> MetricStats:
        if not values:
            return MetricStats()
        p50_val, p75_val, p95_val = np.percentile(values, [50, 75, 95])
        def find_closest_job(target_val):
            if not jobs:
                return None
            idx = min(range(len(values)), key=lambda i: abs(values[i] - target_val))
            return jobs[idx]
        return MetricStats(
            avg=float(np.mean(values)),
            p50=float(p50_val),
            p75=float(p75_val),
            p95=float(p95_val),
            p50_job=find_closest_job(p50_val),
            p75_job=find_closest_job(p75_val),
            p95_job=find_closest_job(p95_val),
        )

    def _calculate_group_stats(self, jobs: List[Dict[str, Any]], group_name: str) -> GroupStats:
        """Calculate stats for a specific group of jobs with service/subtask segmentation."""
        if not jobs:
            return GroupStats(name=group_name, job_count=0)

        durations: Dict[str, List[float]] = {"end_to_end": []}
        valid_jobs = []

        for job in jobs:
            timestamps = job.get("data", {}).get("stage_timestamps", [])
            if len(timestamps) < 2:
                continue
            valid_jobs.append(job)
            
            # End-to-end (first to last timestamp)
            end_to_end = timestamps[-1]["offset_s"] - timestamps[0]["offset_s"]
            durations["end_to_end"].append(end_to_end)
            
            # SERVICE-LEVEL durations (START→END)
            for service_name, (start_stage, end_stage) in SERVICE_BOUNDARIES.items():
                start_idx = next((i for i, ts in enumerate(timestamps) if ts["stage_name"] == start_stage), None)
                end_idx = next((i for i, ts in enumerate(timestamps) if ts["stage_name"] == end_stage), None)
                if start_idx is not None and end_idx is not None and end_idx > start_idx:
                    service_duration = timestamps[end_idx]["offset_s"] - timestamps[start_idx]["offset_s"]
                    durations.setdefault(service_name, []).append(service_duration)
            
            # SUBTASK durations (IN→OUT)
            for subtask_name, (in_stage, out_stage) in SUBTASK_PAIRS.items():
                in_idx = next((i for i, ts in enumerate(timestamps) if ts["stage_name"] == in_stage), None)
                out_idx = next((i for i, ts in enumerate(timestamps) if ts["stage_name"] == out_stage), None)
                if in_idx is not None and out_idx is not None and out_idx > in_idx:
                    subtask_duration = timestamps[out_idx]["offset_s"] - timestamps[in_idx]["offset_s"]
                    durations.setdefault(subtask_name, []).append(subtask_duration)

        stats = GroupStats(
            name=group_name, 
            job_count=len(valid_jobs), 
            raw_durations=durations
        )
        
        if valid_jobs:
            # Overall end-to-end
            stats.end_to_end = self._get_metric_stats(durations["end_to_end"], valid_jobs)
            
            # SERVICE latencies (exactly what you want #1)
            for service_name, values in durations.items():
                if service_name in SERVICE_BOUNDARIES:
                    stats.service_latencies[service_name] = self._get_metric_stats(values, valid_jobs)
            
            # SUBTASK latencies (exactly what you want #2) 
            for subtask_name, values in durations.items():
                if subtask_name in SUBTASK_PAIRS:
                    stats.subtask_latencies[subtask_name] = self._get_metric_stats(values, valid_jobs)

        return stats
    
    def calculate_statistics(self) -> Dict[str, GroupStats]:
        """Segment by job type and calculate statistics for each + overall."""
        user_jobs, background_jobs, all_jobs = [], [], self.successfully_processed_results
        
        for job in all_jobs:
            job_type = job.get("data", {}).get("header", {}).get("type")
            if job_type == "user":
                user_jobs.append(job)
            elif job_type == "background":
                background_jobs.append(job)

        return {
            "ALL": self._calculate_group_stats(all_jobs, "ALL"),
            "USER": self._calculate_group_stats(user_jobs, "USER"),
            "BACKGROUND": self._calculate_group_stats(background_jobs, "BACKGROUND")
        }

    def save_json(self, filepath: str) -> Path:
        """Save complete benchmark results + statistics as JSON."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"benchmark_{timestamp}.json"
        output_path = Path(filepath or "./benchmarks").resolve()
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Prepare serializable data
        serializable = asdict(self)
        serializable["statistics"] = {}
        
        # Add computed statistics - FIXED for new GroupStats fields
        stats = self.calculate_statistics()
        for group_name, group_stats in stats.items():
            serializable["statistics"][group_name] = {
                "job_count": group_stats.job_count,
                "end_to_end": asdict(group_stats.end_to_end),
                "service_latencies": {k: asdict(v) for k, v in group_stats.service_latencies.items()},
                "subtask_latencies": {k: asdict(v) for k, v in group_stats.subtask_latencies.items()},
                "raw_durations": group_stats.raw_durations
            }
        
        # Save raw jobs (unchanged)
        serializable["raw_success_jobs"] = []
        for job in self.successfully_processed_results[:50]:
            job_copy = json.loads(json.dumps(job))
            if "html" in job_copy.get("data", {}).get("payload", {}):
                job_copy["data"]["payload"]["html"] = "[TRUNCATED HTML]"
            serializable["raw_success_jobs"].append(job_copy)
        
        full_path = output_path / filename
        with open(full_path, "w") as f:
            json.dump(serializable, f, indent=2, default=str)
        
        print(f"💾 Saved benchmark results: {full_path}")
        return full_path
    
    def print_report(self) -> None:
        print(f"Jobs submitted: {self.jobs_submitted}")
        print(f"Submit successes: {self.submit_successes}")
        print(f"Submit failures: {self.submit_failures}")
        print(f"Valid results: {len(self.valid_processed_results)}")
        print(f"Invalid results: {len(self.invalid_processed_results)}")
        print(f"Failures processed: {len(self.failure_processed_results)}")
        print(f"Submission latency: {self.time_elapsed_submission:.2f}s")
        print(f"End-to-end wall clock: {self.time_elapsed_processing:.2f}s")

        stats_dict = self.calculate_statistics()
        for group_name, group_stats in stats_dict.items():
            print(f"\n=== {group_name} Jobs (n={group_stats.job_count}) ===")
            print(f"End-to-End: avg={group_stats.end_to_end.avg:.2f}s, "
                f"p50={group_stats.end_to_end.p50:.2f}s, "
                f"p75={group_stats.end_to_end.p75:.2f}s, "
                f"p95={group_stats.end_to_end.p95:.2f}s")
            
            # SERVICE-LEVEL REPORTING
            if group_stats.service_latencies:
                print("\n📊 SERVICE LEVEL (avg/p95):")
                for service_name, metric in sorted(group_stats.service_latencies.items()):
                    print(f"  {service_name:15}: {metric.avg:6.2f}s / p95:{metric.p95:6.2f}s")
            
            # SUBTASK-LEVEL REPORTING  
            if group_stats.subtask_latencies:
                print("\n🔍 TOP 10 SUBTASKS by p95:")
                top_subtasks = sorted(
                    group_stats.subtask_latencies.items(), 
                    key=lambda x: x[1].p95, 
                    reverse=True
                )[:10]
                for subtask_name, metric in top_subtasks:
                    service = subtask_name.split('.')[0]
                    print(f"  {service:12} | {subtask_name:25}: {metric.avg:5.2f}s / p95:{metric.p95:5.2f}s")
                    
class BenchmarkTemplate(ABC):
    """
    A reusable benchmark framework that can:
    - Submit jobs via API or directly into Redis
    - Poll Redis streams for results
    - Measure end-to-end latency
    - Validate correctness
    """

    # Default configuration
    API_URL = "http://api-service:8001/api/v1/jobs"
    REDIS_HOST = "redis"
    REDIS_PORT = 6379
    
    MAX_POLL = 1_000_000
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
    
    def __init__(self, input_stream:str, output_stream:str, failure_streams: List[str], max_workers: int = 20):
        self.max_workers = max_workers
        self.input_stream = input_stream
        self.output_stream = output_stream
        self.failure_streams = failure_streams
        self.consumer_group = "benchmark-consumer"
        print(f"--- Running {self.__class__.__name__} ---")

        self.session = requests.Session()
        self.redis = redis.Redis(host=self.REDIS_HOST, port=self.REDIS_PORT, decode_responses=True)
        self.redis.ping() 
        print(f"[INFO] Connected to Redis on port {self.REDIS_PORT}")
 
    # ----------------------------------------------------------------------
    # ABSTRACT HOOKS
    # ----------------------------------------------------------------------
    def setup(self):
        """Prepare environment, clear Redis streams, create consumer groups."""
        print("🧹 Phase 1: Clearing ALL streams...")
        
        all_streams = [self.input_stream, self.output_stream] + self.failure_streams
        for stream in all_streams:
            try:
                self.redis.xtrim(stream, maxlen=0, approximate=True)
                print(f"  Cleared {stream}")
            except redis.exceptions.ResponseError:
                print(f"  {stream} didn't exist")
        
        print("🛠️ Phase 2: Creating consumer groups ONLY on target streams...")
        target_streams = [self.output_stream] + self.failure_streams  # NO input_stream!
        
        for stream in target_streams:
            # Destroy any existing group
            try:
                self.redis.xgroup_destroy(stream, self.consumer_group)
                print(f"  Destroyed existing group on {stream}")
            except:
                pass
            
            # Create fresh group + stream
            try:
                self.redis.xgroup_create(stream, self.consumer_group, id="$", mkstream=True)
                print(f"  ✓ Created '{self.consumer_group}' on {stream}")
                
                # VERIFY
                groups = self.redis.xinfo_groups(stream)
                assert any(g['name'] == self.consumer_group for g in groups), f"Group missing on {stream}"
                print(f"  Verified: {len(groups)} group(s)")
                
            except Exception as e:
                print(f"  ❌ FAILED {stream}: {e}")
                raise
        
        print(f"✅ Setup complete. Polling: {target_streams}")
        print(f"📡 Input (no group needed): {self.input_stream}")

    @abstractmethod
    def generate_jobs(self) -> List[Dict[str, Any]]:
        """Return a list of job dicts: { 'article_url': ..., 'is_background': ... }"""

    @abstractmethod
    def validate_results(self, successfully_processed_jobs: List[Dict[str, Any]]) -> Tuple[List[Dict[str,Any]], List[Dict[str, Any]]]:
        """validate correctness of results."""
        # return successfully_processed_jobs, [] to skip

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
    def _create_redis_job(self, article_url:str, news_outlet:str = None, is_background: bool = True) -> Message:

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
                type=JobType.BACKGROUND.value if is_background else JobType.USER.value,
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
            print("Failed api job submission")
            return {"error": str(e), "job_create": job_create}

    def _submit_job_redis(self, payload: Message) -> Dict[str, Any]:
        try:
            payload_str = json.dumps(payload.model_dump())
            redis_id = self.redis.xadd(self.input_stream, {"payload": payload_str}, approximate=True)
            return {"redis_id": redis_id, "payload": payload}
        except Exception as e:
            print("Failed redis job submission")
            return {"error": str(e), "payload": payload}

    def _submit_jobs_concurrently(self, jobs: List[Dict[str, Any]]) -> Tuple[List[Any], List[Any]]:
        successes, failures = [], []

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {}
            for job in jobs:
                if job["submission_type"] == "redis":
                    futures[executor.submit(self._submit_job_redis, job["payload"])] = job
                else:
                    futures[executor.submit(self._submit_job_api, job["payload"])] = job

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
        print(submission_result)
        # Redis submissions carry a Message payload
        if "payload" in submission_result and isinstance(submission_result["payload"], Message):
            return submission_result["payload"].header.uid
        
        # API submissions return a response dict
        if "response" in submission_result and "uid" in submission_result["response"]:
            return submission_result["response"]["uid"]
        return None


    def _decode_one_message(self, stream_name:str, redis_message_id:str, fields:Dict[str, Any]) -> Dict[str, Any]:
        """
        Decodes a single raw message from Redis, handling byte conversion and JSON parsing.
        """
        decoded_fields: Dict[str, Any] = fields
        message_data:Dict[str, Any] = {}

        if "payload" in decoded_fields:
            message_data = json.loads(decoded_fields["payload"])
        else:
            print(f"Message {redis_message_id} is missing 'payload' field.")
            message_data = decoded_fields

        return {
            "stream": stream_name,
            "redis_message_id": redis_message_id,
            "data": message_data,
        }

    def _poll_results(self, expected_uids: List[str], timeout_s: float = 3000.0, poll_interval: float = 30.0) -> Dict[str, Dict[str, Any]]:
        poll_count = 0
        expected = set(expected_uids)
        results: Dict[str, Dict[str, Any]] = {}
        start = time.time()
        
        # EXACTLY like your working code
        target_streams = [self.output_stream] + self.failure_streams
        print(f"Waiting for {len(expected)} UIDs, polling: {target_streams}")
        
        while len(results) < len(expected) and (time.time() - start) < timeout_s:
            if poll_count % 10 == 0:
                remaining = len(expected) - len(results)
                print(f"Poll {poll_count}: {len(results)}/{len(expected)} ({remaining} remaining)")
            
            streams_dict = {stream: ">" for stream in target_streams}

            print(f"\t[POLL] Iteration={poll_count}, Streams={streams_dict}, ResultsSoFar={len(results)}")

            try:
                response = self.redis.xreadgroup(
                    self.consumer_group,
                    "benchmark-consumer",
                    streams=streams_dict,  # ← Your exact syntax
                    count=100,
                    block=1000,
                )
                # print(f"[RAW RESPONSE] {response}")

            except redis.exceptions.ResponseError:
                poll_count += 1
                time.sleep(poll_interval)
                continue
            
            if not response:
                poll_count += 1
                time.sleep(poll_interval)
                continue
            
            for stream_name_bytes, messages in response:
                stream_name = stream_name_bytes
                print(f"[STREAM] {stream_name}, MessagesCount={len(messages)}")
                is_failure = stream_name in self.failure_streams
                for redis_message_id_bytes, fields in messages:
                    redis_message_id = redis_message_id_bytes
                    
                    try:
                        message_dict = self._decode_one_message(stream_name, redis_message_id, fields)
                        # print(f"[MESSAGE DECODED] {message_dict}")
                        uid = message_dict["data"]["header"]["uid"]
                        print(f"[UID] {uid}")
                        
                        # Only track new UIDs
                        if uid in expected and uid not in results:
                            message_dict["is_failure"] = is_failure
                            results[uid] = message_dict
                            print(f"✓ Found {uid} in {stream_name}")
                            
                    except Exception as e:
                        print(f"[DECODE ERROR] {redis_message_id}: {e}")
                        continue
            
            poll_count += 1
            time.sleep(poll_interval)
        
        missing = expected - set(results.keys())
        if missing:
            print(f"⚠️ TIMEOUT: Missing {len(missing)} jobs: {list(missing)}")
        
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
        
        if len(submit_successes) == 0:
            for job in submit_failures:
                print(job.get("error"))
            raise Exception("No jobs submitted!")

        print(f"Submitted {len(submit_successes)} jobs successfully, {len(submit_failures)} failed")

        # Extract UIDs
        expected_uids = [self._extract_uid(s) for s in submit_successes if self._extract_uid(s)]
        print("Expected UIDs:", expected_uids)

        if len(expected_uids) == 0:
            print("TEST FAILED")
            self.setup()
            return
        
        # Poll Redis for results
        print("Polling Redis for results...")
        results = self._poll_results(expected_uids)
        
        successfully_processed_jobs = [j for _, j in results.items() if not j.get("is_failure")]
        failure_processed_jobs = [j for _, j in results.items() if j.get("is_failure")]
        elapsed_completion = time.time() - start
        
        # Validate
        valid_jobs, invalid_jobs = self.validate_results(successfully_processed_jobs)
        
        result = BenchmarkResults(
            time_elapsed_submission=elapsed_submission,
            time_elapsed_processing=elapsed_completion,
            jobs_submitted=len(jobs),
            submit_successes=len(submit_successes),
            submit_failures=len(submit_failures),
            successfully_processed_results = successfully_processed_jobs,
            failure_processed_results = failure_processed_jobs,
            valid_processed_results = valid_jobs,
            invalid_processed_results = invalid_jobs
        )
        result.save_json("./tests/benchmarks/reports")
        result.print_report()
