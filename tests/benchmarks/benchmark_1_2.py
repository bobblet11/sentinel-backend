import time

from tests.benchmarks.benchmark_base import BenchmarkResults, BenchmarkTemplate


class Benchmark_1_2(BenchmarkTemplate):
	def __init__(self):
		super().__init__()
	
	def setup(self):
		pass
		
	def execute(self):
		jobs = self.load_articles(10,0, offset=1)
		self._submit_jobs_concurrently(jobs,max_workers=max(len(jobs), 10))



if __name__ == "__main__":
        benchmark = Benchmark_1_2()
        benchmark.execute()
        