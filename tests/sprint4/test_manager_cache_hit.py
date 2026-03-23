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


class TestManagerCacheHit(unittest.TestCase):
    def test_ensure_model_uses_existing_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lock_path = root / "models.lock.json"
            store_root = root / "store"
            _write_manifest(lock_path)

            manager = ModelManager(lock_path=lock_path, store_root=store_root)

            artifact = manager.get_local_path("TEST_MODEL", artifact_name="weights.bin")
            artifact.parent.mkdir(parents=True, exist_ok=True)
            payload = b"already-cached"
            artifact.write_bytes(payload)
            expected_hash = hashlib.sha256(payload).hexdigest()

            download_called = {"count": 0}

            def download_fn(_tmp_path, _spec):
                download_called["count"] += 1

            resolved = manager.ensure_model(
                "TEST_MODEL",
                artifact_name="weights.bin",
                expected_sha256=expected_hash,
                download_fn=download_fn,
            )

            self.assertEqual(resolved, artifact)
            self.assertEqual(download_called["count"], 0)


if __name__ == "__main__":
    unittest.main()
