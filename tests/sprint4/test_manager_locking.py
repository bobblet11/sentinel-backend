import hashlib
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from common.model_manager import ModelManager


def _write_manifest(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "generated_on": "2026-03-13",
                "models": [
                    {
                        "key": "TEST_MODEL",
                        "provider": "huggingface",
                        "model_id": "org/test-model",
                        "task": "unit-test",
                        "source": "tests",
                        "local_path_hint": "models/test-model",
                        "revision": None,
                        "mutable": False,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


class TestManagerLocking(unittest.TestCase):
    def test_concurrent_ensure_model_downloads_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lock_path = root / "models.lock.json"
            store_root = root / "store"
            _write_manifest(lock_path)

            manager = ModelManager(lock_path=lock_path, store_root=store_root)
            payload = b"shared-download"
            expected_hash = hashlib.sha256(payload).hexdigest()

            calls = {"count": 0}
            calls_lock = threading.Lock()
            errors = []
            resolved_paths = []

            def download_fn(tmp_path, _spec):
                with calls_lock:
                    calls["count"] += 1
                time.sleep(0.2)
                tmp_path.parent.mkdir(parents=True, exist_ok=True)
                tmp_path.write_bytes(payload)

            def worker():
                try:
                    path = manager.ensure_model(
                        "TEST_MODEL",
                        artifact_name="weights.bin",
                        expected_sha256=expected_hash,
                        download_fn=download_fn,
                    )
                    resolved_paths.append(path)
                except Exception as exc:
                    errors.append(exc)

            t1 = threading.Thread(target=worker)
            t2 = threading.Thread(target=worker)

            t1.start()
            t2.start()
            t1.join()
            t2.join()

            self.assertEqual(errors, [])
            self.assertEqual(calls["count"], 1)
            self.assertEqual(len(resolved_paths), 2)
            self.assertEqual(resolved_paths[0], resolved_paths[1])
            self.assertTrue(resolved_paths[0].exists())


if __name__ == "__main__":
    unittest.main()
