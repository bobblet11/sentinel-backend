from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Callable

from common.model_manager.exceptions import ModelDownloadError
from common.model_manager.locking import FileLock
from common.model_manager.registry import ModelRegistry, ModelSpec

DownloadFn = Callable[[Path, ModelSpec], None]


class ModelManager:
    """Core model artifact manager backed by models.lock.json."""

    def __init__(
        self,
        lock_path: str | Path,
        store_root: str | Path,
        strict: bool = False,
        lock_timeout_s: float = 30.0,
        lock_poll_interval_s: float = 0.05,
    ):
        self.registry = ModelRegistry(lock_path)
        self.store_root = Path(store_root)
        self.strict = strict
        self.lock_timeout_s = lock_timeout_s
        self.lock_poll_interval_s = lock_poll_interval_s

    def get_spec(self, model_key: str) -> ModelSpec:
        return self.registry.get(model_key)

    def get_local_dir(self, model_key: str) -> Path:
        spec = self.registry.get(model_key)
        return self.store_root / spec.local_path_hint

    def get_local_path(self, model_key: str, artifact_name: str = "artifact.bin") -> Path:
        return self.get_local_dir(model_key) / artifact_name

    def ensure_model(
        self,
        model_key: str,
        artifact_name: str = "artifact.bin",
        expected_sha256: str | None = None,
        download_fn: DownloadFn | None = None,
    ) -> Path:
        target_path = self.get_local_path(model_key, artifact_name)
        if self._is_ready(target_path, expected_sha256):
            return target_path

        lock_path = target_path.parent / ".download.lock"
        with FileLock(
            lock_path,
            timeout_s=self.lock_timeout_s,
            poll_interval_s=self.lock_poll_interval_s,
        ):
            if self._is_ready(target_path, expected_sha256):
                return target_path

            if download_fn is None:
                raise ModelDownloadError(
                    f"Artifact missing for {model_key} and no download function provided"
                )

            target_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = target_path.with_name(f".{target_path.name}.tmp.{os.getpid()}")

            if target_path.exists() and expected_sha256 and not self._hash_matches(target_path, expected_sha256):
                target_path.unlink()

            try:
                download_fn(temp_path, self.registry.get(model_key))
            except Exception as exc:
                if temp_path.exists():
                    temp_path.unlink()
                raise ModelDownloadError(f"Failed to download {model_key}: {exc}") from exc

            if not temp_path.exists():
                raise ModelDownloadError(f"Download function did not create artifact for {model_key}")

            if expected_sha256 and not self._hash_matches(temp_path, expected_sha256):
                temp_path.unlink()
                raise ModelDownloadError(
                    f"Checksum mismatch for {model_key}: expected {expected_sha256}"
                )

            os.replace(temp_path, target_path)

        return target_path

    def _is_ready(self, artifact_path: Path, expected_sha256: str | None) -> bool:
        if not artifact_path.exists():
            return False
        if expected_sha256 is None:
            return True
        return self._hash_matches(artifact_path, expected_sha256)

    @staticmethod
    def _hash_matches(path: Path, expected_sha256: str) -> bool:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest().lower() == expected_sha256.lower()
