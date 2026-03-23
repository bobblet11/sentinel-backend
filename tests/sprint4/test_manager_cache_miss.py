import hashlib
import json
import tempfile
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


class TestManagerCacheMiss(unittest.TestCase):
    def test_ensure_model_downloads_when_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lock_path = root / "models.lock.json"
            store_root = root / "store"
            _write_manifest(lock_path)

            manager = ModelManager(lock_path=lock_path, store_root=store_root)
            payload = b"fresh-download"
            expected_hash = hashlib.sha256(payload).hexdigest()

            calls = {"count": 0}

            def download_fn(tmp_path, _spec):
                calls["count"] += 1
                tmp_path.parent.mkdir(parents=True, exist_ok=True)
                tmp_path.write_bytes(payload)

            resolved = manager.ensure_model(
                "TEST_MODEL",
                artifact_name="weights.bin",
                expected_sha256=expected_hash,
                download_fn=download_fn,
            )

            self.assertTrue(resolved.exists())
            self.assertEqual(resolved.read_bytes(), payload)
            self.assertEqual(calls["count"], 1)


if __name__ == "__main__":
    unittest.main()
