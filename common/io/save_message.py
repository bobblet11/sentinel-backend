import json
import os
from pathlib import Path
from typing import Any, Dict

from filelock import FileLock

from common.models.api.redis_models import StreamMessage


class MessageSaver:
    def __init__(
        self,
        group_name: str = "group",
        message_store_filename: str = "messages.json",
        log_directory: Path = Path("/app/logs"),
    ):
        # create file
        if isinstance(log_directory, str):
            log_directory = Path(log_directory)
            log_directory.mkdir(mode=777, parents=True, exist_ok=True)
        message_store_filepath: Path = log_directory / message_store_filename
        message_store_filepath.touch(mode=777, exist_ok=True)
        os.chmod(str(message_store_filepath), 0o666)
        self.message_store_filepath: Path = message_store_filepath
        self.lock_path = self.message_store_filepath.with_suffix(".lock")
        self.init_json(group_name)
        self.group_name = group_name

    def init_json(self, group_name: str) -> None:
        lock = FileLock(self.lock_path)
        with lock:
            try:
                with open(str(self.message_store_filepath), "r") as file:
                    file_data: Dict[str, Any] = json.load(file)
            except (json.JSONDecodeError, FileNotFoundError):
                file_data = {}

            if group_name not in file_data:
                file_data[group_name] = []

            with open(str(self.message_store_filepath), "w") as file:
                json.dump(file_data, file, indent=4)

    def save_new_message(self, message: StreamMessage) -> None:

        lock = FileLock(self.lock_path)
        with lock:
            new_message_data: Dict[str, Any] = message.data.model_dump()

            try:
                with open(str(self.message_store_filepath), "r") as file:
                    file_data = json.load(file)
            except (json.JSONDecodeError, FileNotFoundError):
                file_data = {self.group_name: []}

            file_data[self.group_name].append(new_message_data)

            with open(str(self.message_store_filepath), "w") as file:
                json.dump(file_data, file, indent=4)
