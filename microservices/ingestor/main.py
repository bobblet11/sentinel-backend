#entry of docker

if __name__ == "__main__":
	# In a real deployment, this would be triggered by a cron job.
	# For our simulation, we can just run it once or in a loop.
	print("Hello worlds")

	# generate our Ingestor instances
	# cron job run for all (multi thread each ingestor)
	pass