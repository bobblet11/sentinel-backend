import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
COMPOSE_PATH = ROOT / "docker" / "compose" / "docker-compose.yml"


def _extract_service_block(compose_text: str, service_name: str) -> str:
    pattern = rf"(?ms)^  {re.escape(service_name)}:\n(.*?)(?=^  [a-zA-Z0-9_-]+:|\Z)"
    match = re.search(pattern, compose_text)
    if not match:
        raise AssertionError(f"Service block not found: {service_name}")
    return match.group(1)


class TestComposeVolumeMounts(unittest.TestCase):
    def test_compose_file_exists(self):
        self.assertTrue(COMPOSE_PATH.exists(), f"Missing {COMPOSE_PATH}")

    def test_nlp_and_retrieval_mount_model_store(self):
        compose_text = COMPOSE_PATH.read_text(encoding="utf-8")
        nlp_block = _extract_service_block(compose_text, "nlp-service")
        retrieval_block = _extract_service_block(compose_text, "retrieval-layer-service")

        self.assertIn("model-store:/opt/sentinel/models", nlp_block)
        self.assertIn("model-store:/opt/sentinel/models", retrieval_block)

    def test_nlp_and_retrieval_have_model_env_vars(self):
        compose_text = COMPOSE_PATH.read_text(encoding="utf-8")
        nlp_block = _extract_service_block(compose_text, "nlp-service")
        retrieval_block = _extract_service_block(compose_text, "retrieval-layer-service")

        expected_lines = [
            "MODEL_LOCK_PATH=${MODEL_LOCK_PATH:-/app/configs/models.lock.json}",
            "MODEL_STORE_ROOT=${MODEL_STORE_ROOT:-/opt/sentinel/models}",
            "MODEL_STRICT=${MODEL_STRICT:-false}",
            "HF_HOME=${HF_HOME:-/opt/sentinel/models/huggingface}",
            "TRANSFORMERS_CACHE=${TRANSFORMERS_CACHE:-/opt/sentinel/models/huggingface}",
            "SENTENCE_TRANSFORMERS_HOME=${SENTENCE_TRANSFORMERS_HOME:-/opt/sentinel/models/sentence_transformers}",
        ]

        for line in expected_lines:
            self.assertIn(line, nlp_block)
            self.assertIn(line, retrieval_block)

    def test_top_level_declares_model_store_volume(self):
        compose_text = COMPOSE_PATH.read_text(encoding="utf-8")
        self.assertRegex(compose_text, r"(?m)^volumes:\n(?:.*\n)*?  model-store:\s*$")


if __name__ == "__main__":
    unittest.main()
