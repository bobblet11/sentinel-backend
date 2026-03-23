import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "configs" / "models.lock.json"


class TestModelManifestSchema(unittest.TestCase):
    def test_manifest_file_exists(self):
        self.assertTrue(MANIFEST_PATH.exists(), f"Missing manifest: {MANIFEST_PATH}")

    def test_manifest_top_level_shape(self):
        data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

        self.assertIsInstance(data, dict)
        self.assertEqual(data.get("schema_version"), "1.0.0")
        self.assertIn("generated_on", data)
        self.assertIn("models", data)
        self.assertIsInstance(data["models"], list)
        self.assertGreater(len(data["models"]), 0)

    def test_manifest_entries_have_required_fields(self):
        data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        required_fields = {
            "key",
            "provider",
            "model_id",
            "task",
            "source",
            "local_path_hint",
            "revision",
            "mutable",
        }

        for idx, entry in enumerate(data["models"]):
            self.assertIsInstance(entry, dict, f"Entry #{idx} must be a dict")
            self.assertTrue(required_fields.issubset(entry.keys()), f"Entry #{idx} missing required fields")
            self.assertIsInstance(entry["key"], str)
            self.assertIsInstance(entry["provider"], str)
            self.assertIn(entry["provider"], {"huggingface", "spacy"})
            self.assertIsInstance(entry["model_id"], str)
            self.assertNotEqual(entry["model_id"].strip(), "")
            self.assertIsInstance(entry["task"], str)
            self.assertIsInstance(entry["source"], str)
            self.assertIsInstance(entry["local_path_hint"], str)
            self.assertIn("/", entry["local_path_hint"])
            self.assertIsInstance(entry["mutable"], bool)

    def test_manifest_keys_are_unique(self):
        data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        keys = [entry["key"] for entry in data["models"]]
        self.assertEqual(len(keys), len(set(keys)), "Manifest keys must be unique")


if __name__ == "__main__":
    unittest.main()
