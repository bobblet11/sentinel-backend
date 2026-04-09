# microservices/nlp/components/device.py
"""
Unified device configuration for all NLP pipeline components.

Resolves GPU/CPU once at startup and provides a frozen config object
that every component accepts — no more per-component detection.
"""

import platform
from dataclasses import dataclass
from logging import getLogger

import torch

logger = getLogger("NLP")


@dataclass(frozen=True)
class DeviceConfig:
    """Immutable snapshot of the resolved compute device and dtype settings."""

    device: str  # "cuda", "mps", or "cpu"
    device_id: int  # 0 for cuda, -1 for cpu/mps
    use_fp16: bool  # True only when CUDA is available
    dtype: torch.dtype  # float16 when fp16, else float32

    @staticmethod
    def resolve(use_gpu: bool = True) -> "DeviceConfig":
        """
        Resolve the best available device.

        Priority: CUDA > MPS (macOS) > CPU.
        Falls back to CPU with a warning if GPU is requested but unavailable.
        """
        if use_gpu and torch.cuda.is_available():
            logger.info("DeviceConfig: CUDA available — using GPU with fp16.")
            return DeviceConfig(
                device="cuda", device_id=0, use_fp16=True, dtype=torch.float16
            )

        if (
            use_gpu
            and platform.system() == "Darwin"
            and torch.backends.mps.is_available()
        ):
            logger.info(
                "DeviceConfig: MPS available — using Apple GPU (fp32 only)."
            )
            return DeviceConfig(
                device="mps", device_id=-1, use_fp16=False, dtype=torch.float32
            )

        if use_gpu:
            logger.warning(
                "DeviceConfig: GPU requested but unavailable — falling back to CPU."
            )
        else:
            logger.info("DeviceConfig: Using CPU (GPU not requested).")

        return DeviceConfig(
            device="cpu", device_id=-1, use_fp16=False, dtype=torch.float32
        )

    @property
    def device_map(self) -> dict:
        """For transformers ``from_pretrained(device_map=...)`` calls."""
        return {"": self.device}

    @property
    def is_gpu(self) -> bool:
        return self.device in ("cuda", "mps")

    def __repr__(self) -> str:
        return (
            f"DeviceConfig(device={self.device!r}, fp16={self.use_fp16}, "
            f"dtype={self.dtype})"
        )
