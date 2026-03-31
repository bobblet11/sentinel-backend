import json
import os
from pathlib import Path
from typing import Any, Dict, Tuple, List
from common.models.api.redis_models import StreamMessage
from filelock import FileLock 


class JsonHandler():
    def __init__(self, filename: str = "messages.json", log_directory:Path=Path("/app/logs")):    
        # Create JSON file
        if isinstance(log_directory, str):
            log_directory = Path(log_directory)
            log_directory.mkdir(mode=777,parents=True, exist_ok=True)
        filepath:Path = log_directory / filename
        filepath.touch(mode=777, exist_ok=True)
        os.chmod(str(filepath), 0o666)
        self.filepath: Path = filepath
        
        # Create locks on the files
        lockpath:Path = log_directory / "stats.lock"
        lockpath.touch(mode=777, exist_ok=True)
        os.chmod(str(lockpath), 0o666)
        self.lock_path = lockpath


    def read_json(self) -> Dict[str,Any]:
        lock = FileLock(self.lock_path)
        with lock:
            file_data = {}
            try:
                with open(str(self.filepath), "r") as file:
                    file_data = json.load(file)
            except (json.JSONDecodeError, FileNotFoundError):
                file_data = {}
            return file_data
        

    def write_json(self, file_data:Dict[str,Any]) -> None:
        lock = FileLock(self.lock_path)
        with lock:
            with open(str(self.filepath), "w") as file:
                json.dump(file_data, file, indent=4)
