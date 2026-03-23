import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ENV_TEMPLATE = ROOT / "configs" / ".env.template"
BENCHMARK_ENV = ROOT / "configs" / "benchmark-1" / ".env"

REQUIRED_MODEL_ENV_KEYS = {
    "MODEL_LOCK_PATH",
    "MODEL_STORE_ROOT",
    "MODEL_STRICT",
    "HF_HOME",
    "TRANSFORMERS_CACHE",
    "SENTENCE_TRANSFORMERS_HOME",
}


def _parse_env_file(path: Path) -> dict[str, str]:
    env_map: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        env_map[key.strip()] = value.strip()
    return env_map


class TestEnvResolution(unittest.TestCase):
    def test_env_files_exist(self):
        self.assertTrue(ENV_TEMPLATE.exists(), f"Missing {ENV_TEMPLATE}")
        self.assertTrue(BENCHMARK_ENV.exists(), f"Missing {BENCHMARK_ENV}")

    def test_template_has_required_model_env_keys(self):
        env_map = _parse_env_file(ENV_TEMPLATE)
        missing = sorted(REQUIRED_MODEL_ENV_KEYS - set(env_map.keys()))
        self.assertEqual(missing, [], f".env.template missing keys: {missing}")

    def test_benchmark_has_required_model_env_keys(self):
        env_map = _parse_env_file(BENCHMARK_ENV)
        missing = sorted(REQUIRED_MODEL_ENV_KEYS - set(env_map.keys()))
        self.assertEqual(missing, [], f"benchmark .env missing keys: {missing}")

    def test_env_paths_are_consistent(self):
        template_map = _parse_env_file(ENV_TEMPLATE)
        benchmark_map = _parse_env_file(BENCHMARK_ENV)

        self.assertEqual(template_map["MODEL_LOCK_PATH"], "/app/configs/models.lock.json")
        self.assertEqual(benchmark_map["MODEL_LOCK_PATH"], "/app/configs/models.lock.json")

        self.assertEqual(template_map["MODEL_STORE_ROOT"], "/opt/sentinel/models")
        self.assertEqual(benchmark_map["MODEL_STORE_ROOT"], "/opt/sentinel/models")

        self.assertEqual(template_map["HF_HOME"], "/opt/sentinel/models/huggingface")
        self.assertEqual(benchmark_map["HF_HOME"], "/opt/sentinel/models/huggingface")


if __name__ == "__main__":
    unittest.main()
