import time

from tests.benchmarks.benchmark_base import BenchmarkResults, BenchmarkTemplate


class Benchmark_2_1(BenchmarkTemplate):
	def __init__(self):
		super().__init__()
	
	def setup(self):
		pass
		
	def execute(self):
		jobs = self.load_articles(no_user_articles=0,no_background_articles=20, offset=0)
		self._submit_jobs_concurrently(jobs,max_workers=max(len(jobs), 10))

if __name__ == "__main__":
        benchmark = Benchmark_2_1()
        benchmark.execute()
        