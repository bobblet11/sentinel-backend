import time
from math import e
from random import uniform

# make this a function wrapper
# something like this idk
def retry(max_attempts = 3, delay_s = 1): 
	def decorator_retry(func):
		def wrapper(*args, **kwargs):
			for attempt in range(1, max_attempts+1):
				try:
					print(f"Attempt #{attempt}")
					return func(*args, **kwargs)
				except Exception as e:
					if attempt == max_attempts:
						print(f"Fatal failure at attempt {attempt}. Exiting...")
						raise e

					print(f"Failure at attempt {attempt}. Will retry in {delay_s} ms")
					time.sleep(delay_s)
		return wrapper
	return decorator_retry
     
     
def exponential_retry(max_attempts = 3, initial_delay_s = 1, growth_modifier = 1, growth_rate = 1, jitter=True): 
	def decorator_exponential_retry(func):
		def wrapper(*args, **kwargs):
			for attempt in range(1, max_attempts+1):
				try:
					print(f"Attempt #{attempt}")
					return func(*args, **kwargs)
				except Exception as e:
					if attempt == max_attempts:
						print(f"Fatal failure at attempt {attempt}. Exiting...")
						raise e

					time_to_wait_s =  (growth_modifier * pow(e, attempt * growth_rate)) + initial_delay_s
					if jitter:
						time_to_wait_s = uniform(0, time_to_wait_s)

					print(f"Failure at attempt {attempt}. Will retry in {time_to_wait_s} ms")
					time.sleep(time_to_wait_s)
		return wrapper
	return decorator_exponential_retry
