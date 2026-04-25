
from tests.benchmarks.benchmark_base import BenchmarkTemplate


class Benchmark_1_1(BenchmarkTemplate):
	def __init__(self):
		super().__init__()
	
	def setup(self):
		pass
		
	def execute(self):
		jobs = self.load_articles(1,0,offset=0)
		self._submit_jobs_concurrently(jobs,max_workers=max(len(jobs), 1))



if __name__ == "__main__":
        benchmark = Benchmark_1_1()
        benchmark.execute()
        