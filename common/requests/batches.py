import concurrent.futures

class Batch:
	def __init__(self, id, items):
		"""
		Format of a batch
		"""
		self.id = id
		self.items = items
		self.size = len(items)
	
		self.completed = False
		self.result = None

	def set_completed(self, result):
		self.completed = True
		self.result = result

def split_into_batches(items, batch_size): 
	for i in range(0, len(items), batch_size):
		yield Batch(i, items[i:i + batch_size]	)
  
#wrapper
def batch_action(items, batch_size, action):
        for batch in split_into_batches(items, batch_size):
                output_batch = action(batch)
                yield output_batch
  
#wrapper
#action must take a batch as sole argument. other args can be filled in at defintion time.
#action mus return a completed Batch?
def multithreaded_batch_action(items, batch_size, action):
	with concurrent.futures.ThreadPoolExecutor() as executor:
		batches_to_execute = executor.map(action, split_into_batches(items, batch_size))

		for output_batch in batches_to_execute:
			yield output_batch