from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class ModelState(Enum):
    UNLOADED = "unloaded"
    LOADING = "loading"
    READY = "ready"
    ERROR = "error"


class DevicePolicy(Enum):
    CPU_ONLY = "cpu_only"
    PREFER_GPU = "prefer_gpu"
    GPU_REQUIRED = "gpu_required"


@dataclass
class ModelEntry:
    key: str
    model_name: str
    task_type: str
    owner_component: str
    loader: str  # "spacy", "sentence_transformer", "transformers_pipeline", "auto_model_seq2seq", "auto_tokenizer"
    device_policy: DevicePolicy = DevicePolicy.PREFER_GPU
    env_var: Optional[str] = None
    loader_kwargs: Dict[str, Any] = field(default_factory=dict)
    required: bool = True
    estimated_memory_mb: int = 0
    state: ModelState = ModelState.UNLOADED
    instance: Any = None
    error: Optional[Exception] = None
