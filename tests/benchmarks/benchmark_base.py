from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import random
import time
import requests
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple
from urllib.parse import urlparse




@dataclass()
class BenchmarkResults():
        total_time_elapsed:float

TOTAL_ARTICLES_IN_POOL:int = 7372
API_URL = "http://192.168.0.101:8001/api/v1/jobs"
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://sentinel_user:your_secure_password@localhost:5432/sentinel_db")
POLL_INTERVAL_S = 0.5
ARTICLES_PATH = Path("tests/articles/articles.jsonl")

class BenchmarkTemplate(ABC):
	def __init__(self):
		print(f"--- Running {self.__class__.__name__} ---")
		print(f"Targeting API: {API_URL}")
		self.session = requests.Session()
		self.api_url = API_URL


	def _submit_job(self, article: Dict[str, Any], is_user_facing: bool) -> Dict[str, Any]:
		"""
		Submits a single job to the API with a specified priority.
		"""
		payload = {
			"article_url": article["link"],
			"is_background": not is_user_facing
		}
  
		try:
			response = self.session.post(self.api_url, json=payload, timeout=15)
			response.raise_for_status()
			return response.json()
		except requests.exceptions.RequestException as e:
			# Provide more context in the error message
			job_type = "USER" if is_user_facing else "BACKGROUND"
			print(f"API submission failed for {job_type} job {article['link']}: {e}")
			raise e
	
	def _submit_jobs_concurrently(
        self,
        jobs_to_submit: List[Tuple[Dict[str, Any], bool]],
        max_workers: int
    	) -> Tuple[List[Dict[str, Any]], List[Exception]]:
		"""
		Submits a mixed list of user and background jobs in parallel.
		"""
		successes = []
		failures = []

		print(f"Submitting {len(jobs_to_submit)} mixed jobs with a concurrency of {max_workers}...")

		with ThreadPoolExecutor(max_workers=max_workers) as executor:
			future_to_job = {
				executor.submit(self._submit_job, article, is_user_facing): (article, is_user_facing)
				for article, is_user_facing in jobs_to_submit
			}

			for i, future in enumerate(as_completed(future_to_job)):
				try:
					result = future.result()
					successes.append(result)
				except Exception as e:
					failures.append(e)

				print(f"  Progress: {i + 1}/{len(jobs_to_submit)} completed.", end='\r')

			print(f"\nSubmission swarm complete. Successes: {len(successes)}, Failures: {len(failures)}")
		return successes, failures
 
 
	def load_articles(self, no_user_articles:int, no_background_articles, offset:int)-> List:
		if no_user_articles + no_background_articles > TOTAL_ARTICLES_IN_POOL:
			print("FAILURE: too many articles requested for benchmark")
   
		user_articles = []
		background_articles = []
   
		with open(str(ARTICLES_PATH), 'r') as file:
			for current_line_num, line in enumerate(file, start=1):
				if current_line_num <= offset:
					continue
				if current_line_num <= offset + no_user_articles:
					user_articles.append(json.loads(line))
				elif current_line_num <= offset + no_user_articles + no_background_articles:
					background_articles.append(json.loads(line))
				else:
					break

		user_jobs = [(article, True) for article in user_articles]
		background_jobs = [(article, False) for article in background_articles]
		jobs_to_submit = user_jobs + background_jobs
		random.shuffle(jobs_to_submit)
		return jobs_to_submit


	@abstractmethod
	def setup(self):
		pass
		
	@abstractmethod
	def execute(self):
		pass

	def run(self) -> BenchmarkResults:
		self.setup()
		start_time = time.perf_counter()
		self.execute()
		end_time = time.perf_counter()
		BenchmarkResults(total_time_elapsed=end_time - start_time)
		
