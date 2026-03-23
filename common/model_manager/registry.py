from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from common.model_manager.exceptions import ModelNotFoundError


@dataclass(frozen=True)
class ModelSpec:
    key: str
    provider: str
    model_id: str
    task: str
    source: str
    local_path_hint: str
    revision: str | None
    mutable: bool


class ModelRegistry:
    """Loads and resolves model specs from a lock manifest."""

    def __init__(self, lock_path: str | Path):
        self.lock_path = Path(lock_path)
        self._data = self._load_manifest()
        self._specs_by_key = self._build_spec_map()

    def _load_manifest(self) -> dict[str, Any]:
        if not self.lock_path.exists():
            raise FileNotFoundError(f"Model lock file not found: {self.lock_path}")

        raw = self.lock_path.read_text(encoding="utf-8")
        parsed = json.loads(raw)

        if not isinstance(parsed, dict) or "models" not in parsed:
            raise ValueError("Invalid model lock file: expected top-level 'models' list")

        if not isinstance(parsed["models"], list):
            raise ValueError("Invalid model lock file: 'models' must be a list")

        return parsed

    def _build_spec_map(self) -> dict[str, ModelSpec]:
        specs: dict[str, ModelSpec] = {}

        for entry in self._data["models"]:
            spec = ModelSpec(
                key=entry["key"],
                provider=entry["provider"],
                model_id=entry["model_id"],
                task=entry["task"],
                source=entry["source"],
                local_path_hint=entry["local_path_hint"],
                revision=entry.get("revision"),
                mutable=bool(entry.get("mutable", False)),
            )
            specs[spec.key] = spec

        return specs

    def get(self, model_key: str) -> ModelSpec:
        spec = self._specs_by_key.get(model_key)
        if spec is None:
            raise ModelNotFoundError(f"Unknown model key: {model_key}")
        return spec

    def has(self, model_key: str) -> bool:
        return model_key in self._specs_by_key

    def all_keys(self) -> list[str]:
        return sorted(self._specs_by_key.keys())
