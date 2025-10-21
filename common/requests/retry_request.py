# make this a function wrapper
# something like this idk
def retry(max_attempts = 3, delay_ms = 1000, action, **args, **kwargs): 
	for attempt in range(1, max_attempts+1):
		try:
                	print(f"Attempt #{attempt}")
			return action(args, kwargs)

		except Exception as e:
			if attempt == max_attempts:
				print(f"Fatal failure at attempt {attempt}. Exiting...")
				raise e

			print(f"Failure at attempt {attempt}. Will retry in {delay_ms} ms")
			time.sleep(delay_ms)
   

def exponential_retry(max_attempts = 3, initial_delay_ms = 1000, growth_modifier = 1, growth_rate = 1, action, **args, **kwargs): 
	for attempt in range(1, max_attempts+1):
		try:
                	print(f"Attempt #{attempt}")
			return action(args, kwargs)

		except Exception as e:
			if attempt == max_attempts:
				print(f"Fatal failure at attempt {attempt}. Exiting...")
				raise e

			time_to_wait = (growth_modifier * pow(2.17, attempt * growth_rate)) + initial_delay_ms
			print(f"Failure at attempt {attempt}. Will retry in {time_to_wait} ms")
			time.sleep(time_to_wait)
			
			
