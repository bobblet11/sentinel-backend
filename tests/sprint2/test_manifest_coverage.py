import ast
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "configs" / "models.lock.json"
NLP_CONFIG_PATH = ROOT / "microservices" / "nlp" / "config.py"
RETRIEVAL_NLI_PATH = ROOT / "microservices" / "retrieval_layer" / "retrieval" / "nli.py"
NLP_COMPONENTS_DIR = ROOT / "microservices" / "nlp" / "components"


def _load_manifest_model_ids() -> set[str]:
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {entry["model_id"] for entry in data["models"]}


def _collect_nlp_config_model_ids() -> set[str]:
    tree = ast.parse(NLP_CONFIG_PATH.read_text(encoding="utf-8"))
    model_ids: set[str] = set()

    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not isinstance(node.value, ast.Constant) or not isinstance(node.value.value, str):
            continue

        for target in node.targets:
            if isinstance(target, ast.Name) and target.id.endswith("_MODEL"):
                model_ids.add(node.value.value)

    return model_ids


def _collect_retrieval_nli_model_ids() -> set[str]:
    source = RETRIEVAL_NLI_PATH.read_text(encoding="utf-8")
    return set(re.findall(r'model\s*=\s*["\']([^"\']+)["\']', source))


def _collect_spacy_model_ids() -> set[str]:
    model_ids: set[str] = set()
    pattern = re.compile(r'spacy\.load\(\s*["\']([^"\']+)["\']')

    for py_file in NLP_COMPONENTS_DIR.glob("*.py"):
        source = py_file.read_text(encoding="utf-8")
        model_ids.update(pattern.findall(source))

    return model_ids


class TestModelManifestCoverage(unittest.TestCase):
    def test_manifest_covers_all_runtime_model_references(self):
        manifest_ids = _load_manifest_model_ids()

        required_ids = set()
        required_ids.update(_collect_nlp_config_model_ids())
        required_ids.update(_collect_retrieval_nli_model_ids())
        required_ids.update(_collect_spacy_model_ids())

        missing = sorted(required_ids - manifest_ids)
        self.assertEqual(
            missing,
            [],
            f"models.lock.json is missing runtime model IDs: {missing}",
        )

    def test_manifest_has_no_empty_model_ids(self):
        manifest_ids = _load_manifest_model_ids()
        self.assertTrue(all(model_id.strip() for model_id in manifest_ids))


if __name__ == "__main__":
    unittest.main()
