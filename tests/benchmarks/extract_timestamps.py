import json
from pathlib import Path
from typing import List


KEY = "scrape_group"
BENCHMARK_RESULT_1 = Path("tests/logs/benchmark-1-1.json")
BENCHMARK_RESULT_2 = Path("tests/logs/benchmark-1-2.json")
BENCHMARK_RESULT_3 = Path("tests/logs/benchmark-1-3.json")

def load_results(result_path:Path)-> List:
        
	timestamps = []
	file_data = None
	with open(str(result_path), "r") as file:
		file_data = json.load(file)
  
	for obj in file_data[KEY]:
		timestamps.append({           
                     "header" : obj["header"],
                     "stage_timestamps": obj["stage_timestamps"]
                })

	new_file_path = str(result_path).replace(".json", "") + "_timestamps.json"
	new_data = {
		KEY : timestamps
	}
 
	with open(str(new_file_path), "w") as file:
		json.dump(new_data, file, indent=4)
        
if __name__ == "__main__":
        load_results(BENCHMARK_RESULT_1)
        load_results(BENCHMARK_RESULT_2)
        load_results(BENCHMARK_RESULT_3)
