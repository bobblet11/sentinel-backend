from __future__ import annotations

import fcntl
import time
from pathlib import Path

from common.model_manager.exceptions import ModelLockTimeoutError


class FileLock:
    """Simple advisory file lock for coordinating model downloads."""

    def __init__(self, lock_file: str | Path, timeout_s: float = 30.0, poll_interval_s: float = 0.05):
        self.lock_file = Path(lock_file)
        self.timeout_s = timeout_s
        self.poll_interval_s = poll_interval_s
        self._handle = None

    def __enter__(self) -> "FileLock":
        self.lock_file.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.lock_file.open("a+")

        deadline = time.monotonic() + self.timeout_s
        while True:
            try:
                fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    self._handle.close()
                    self._handle = None
                    raise ModelLockTimeoutError(
                        f"Timed out waiting for lock: {self.lock_file}"
                    )
                time.sleep(self.poll_interval_s)

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._handle is not None:
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
            self._handle.close()
            self._handle = None
