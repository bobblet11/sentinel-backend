"""Tests for the ModelManager core lifecycle (no real models required)."""
import pytest

from common.model_manager.exceptions import ModelLoadError, ModelNotReadyError
from common.model_manager.manager import ModelManager
from common.model_manager.registry import DevicePolicy, ModelEntry, ModelState


def _mock_entry(key="TEST_MODEL"):
    return ModelEntry(
        key=key,
        model_name="mock/model",
        task_type="mock",
        owner_component="TestComponent",
        loader="mock",
        device_policy=DevicePolicy.CPU_ONLY,
        required=True,
        estimated_memory_mb=10,
    )


def test_register_and_state():
    mm = ModelManager(device="cpu", dummy_mode=False)
    entry = _mock_entry()
    mm.register(entry)
    assert mm.get_state("TEST_MODEL") == ModelState.UNLOADED


def test_load_success(monkeypatch):
    mm = ModelManager(device="cpu", dummy_mode=False)
    entry = _mock_entry()
    mm.register(entry)
    monkeypatch.setattr(mm, "_load_model", lambda e: "mock_instance")
    mm.load("TEST_MODEL")
    assert mm.get_state("TEST_MODEL") == ModelState.READY
    assert mm.get("TEST_MODEL") == "mock_instance"


def test_load_error(monkeypatch):
    mm = ModelManager(device="cpu", dummy_mode=False)
    entry = _mock_entry()
    mm.register(entry)

    def _fail(e):
        raise RuntimeError("load failed")

    monkeypatch.setattr(mm, "_load_model", _fail)
    mm.load("TEST_MODEL")
    assert mm.get_state("TEST_MODEL") == ModelState.ERROR
    with pytest.raises(ModelLoadError):
        mm.get("TEST_MODEL")


def test_dummy_mode_skips_loading(monkeypatch):
    mm = ModelManager(device="cpu", dummy_mode=True)
    entry = _mock_entry()
    mm.register(entry)
    loaded = []
    monkeypatch.setattr(mm, "_load_model", lambda e: loaded.append(e.key) or "x")
    mm.load_all()
    assert len(loaded) == 0
    assert mm.get_state("TEST_MODEL") == ModelState.UNLOADED


def test_health_check():
    mm = ModelManager(device="cpu", dummy_mode=False)
    mm.register(_mock_entry("M1"))
    mm.register(_mock_entry("M2"))
    health = mm.health_check()
    assert health == {"M1": "unloaded", "M2": "unloaded"}


def test_unload():
    mm = ModelManager(device="cpu", dummy_mode=False)
    entry = _mock_entry()
    mm.register(entry)
    entry.state = ModelState.READY
    entry.instance = "fake"
    mm.unload("TEST_MODEL")
    assert mm.get_state("TEST_MODEL") == ModelState.UNLOADED
    assert entry.instance is None
