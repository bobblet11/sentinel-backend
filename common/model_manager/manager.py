"""Centralized ML model lifecycle management for the NLP pipeline.

This module provides a thread-safe ModelManager singleton that handles model
registration, loading (with sequential GPU loading to prevent meta-device state
corruption), retrieval with blocking during load operations, health reporting,
and resource cleanup. Models are cached in memory after successful loading to
avoid redundant I/O and initialization overhead.

The manager respects device policies per model (CPU_ONLY, PREFER_GPU) and
automatically resolves device placement based on system configuration and model
requirements. GPU models are loaded with fp16 precision when CUDA is available
to reduce memory footprint.

Key features:
    - Singleton model cache with thread-safe blocking during load operations.
    - Device-aware loading: GPU models use cuda:0 with fp16 precision; CPU
      models force CPU placement regardless of system device.
    - Sequential model loading to eliminate meta-device state corruption bugs
      in transformers >= 4.38 (which uses init_empty_weights() internally).
    - HuggingFace cache validation to detect and clean corrupted downloads.
    - Flexible loader dispatch: spacy, sentence_transformer, transformers
      pipelines, and seq2seq/QA models.

Typical usage:
    manager = ModelManager(device="cuda", dummy_mode=False)
    manager.register_defaults()
    manager.load_all()
    embedder = manager.get("EMBEDDING")
"""

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from common.model_manager.exceptions import (
    ModelLoadError,
    ModelNotFoundError,
    ModelNotReadyError,
)
from common.model_manager.registry import DevicePolicy, ModelEntry, ModelState

logger = logging.getLogger(__name__)


class ModelManager:
    """Singleton model cache manager with device configuration and lifecycle control.

    Manages the full lifecycle of ML models: registration, device-aware loading,
    thread-safe retrieval with blocking during load operations, state tracking,
    health reporting, and cleanup. Implements a caching strategy to store loaded
    models in memory and avoid redundant I/O.

    Device placement logic:
        - Models with DevicePolicy.CPU_ONLY are always loaded to CPU.
        - Models with DevicePolicy.PREFER_GPU use the instance device (cuda or cpu).
        - GPU models (device == "cuda") are loaded with float16 precision to
          reduce memory footprint.
        - Sequential loading on GPU prevents meta-device state corruption bugs.

    Thread safety: Uses threading.Event objects per model key to block get() calls
    until a model transitions from LOADING to READY or ERROR state.

    Typical flow:
        1. Instantiate: manager = ModelManager(device="cuda")
        2. Register: manager.register_defaults()
        3. Load: manager.load_all()  # Sequential; respects dummy_mode
        4. Retrieve: model = manager.get("EMBEDDING")  # Blocks if loading
        5. Cleanup: manager.unload_all()
    """

    def __init__(self, device: str = "cpu", dummy_mode: bool = False) -> None:
        """Initialize the ModelManager with device configuration.

        Args:
            device: Target device for GPU-supported models ("cuda" or "cpu").
                    CPU_ONLY models always use CPU regardless of this setting.
            dummy_mode: If True, skip all model loading. Used for testing and
                       local development without GPU/large model dependencies.
        """
        self._device = device
        self._dummy_mode = dummy_mode
        self._registry: Dict[str, ModelEntry] = {}
        self._events: Dict[str, threading.Event] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, entry: ModelEntry) -> None:
        """Register a ModelEntry in the internal registry.

        Args:
            entry: ModelEntry with key, model_name, task_type, device_policy, etc.

        Raises:
            ValueError: If the entry key is already registered (overwrites silently).
        """
        self._registry[entry.key] = entry
        self._events[entry.key] = threading.Event()

    def register_defaults(self) -> None:
        """Register all default NLP pipeline models from environment or hardcoded defaults.

        Registers 6 core models (SPACY_SENT, EMBEDDING, BIAS_POLITICAL, BIAS_SENTIMENT,
        NER, CHECKWORTHY) plus optional decontextualization models if
        ENABLE_DECONTEXTUALIZATION=true. Each model specifies device_policy,
        estimated_memory_mb, and loader dispatch type.

        Models are registered in order of memory footprint (smallest first) to
        surface OOM failures early on memory-limited devices when load_all() runs.
        """
        defaults = [
            ModelEntry(
                key="SPACY_SENT",
                model_name="en_core_web_sm",
                task_type="spacy_nlp",
                owner_component="Preprocessor",
                loader="spacy",
                device_policy=DevicePolicy.CPU_ONLY,
                loader_kwargs={"disable": ["ner", "lemmatizer"]},
                required=True,
                estimated_memory_mb=50,
            ),
            ModelEntry(
                key="EMBEDDING",
                model_name=os.environ.get(
                    "NLP_EMBEDDING_MODEL",
                    "sentence-transformers/all-mpnet-base-v2",
                ),
                task_type="sentence_embedding",
                owner_component="Embedder",
                loader="sentence_transformer",
                device_policy=DevicePolicy.PREFER_GPU,
                required=True,
                estimated_memory_mb=400,
            ),
            # ── Bias Detection (two models) ───────────────────────────────
            ModelEntry(
                key="BIAS_POLITICAL",
                model_name=os.environ.get(
                    "NLP_BIAS_MODEL",
                    "premsa/political-bias-prediction-allsides-BERT",
                ),
                task_type="text_classification",
                owner_component="BiasDetector",
                loader="transformers_pipeline",
                device_policy=DevicePolicy.PREFER_GPU,
                required=False,
                estimated_memory_mb=440,
                loader_kwargs={"top_k": None, "truncation": True, "max_length": 512},
            ),
            ModelEntry(
                key="BIAS_SENTIMENT",
                model_name=os.environ.get(
                    "NLP_SENTIMENT_MODEL",
                    "cardiffnlp/twitter-roberta-base-sentiment-latest",
                ),
                task_type="sentiment_analysis",
                owner_component="BiasDetector",
                loader="transformers_pipeline",
                device_policy=DevicePolicy.PREFER_GPU,
                loader_kwargs={"truncation": True, "max_length": 128},
                required=False,
                estimated_memory_mb=500,
            ),
            ModelEntry(
                key="NER",
                model_name=os.environ.get(
                    "NLP_NER_MODEL",
                    "dslim/bert-base-NER-uncased",
                ),
                task_type="token_classification",
                owner_component="EntityRecognizer",
                loader="transformers_pipeline",
                device_policy=DevicePolicy.PREFER_GPU,
                loader_kwargs={"aggregation_strategy": "simple", "batch_size": 16},
                required=True,
                estimated_memory_mb=420,
            ),
            ModelEntry(
                key="CHECKWORTHY",
                model_name=os.environ.get(
                    "NLP_CHECKWORTHY_MODEL",
                    "whispAI/ClaimBuster-DeBERTaV2",
                ),
                task_type="text_classification",
                owner_component="CheckWorthinessFilter",
                loader="transformers_pipeline",
                device_policy=DevicePolicy.PREFER_GPU,
                required=True,
                estimated_memory_mb=750,
                loader_kwargs={"top_k": None},
            ),
        ]

        enable_decontextualization = os.environ.get(
            "ENABLE_DECONTEXTUALIZATION", "true"
        ).lower() in {"1", "true", "yes", "y"}
        if enable_decontextualization:
            defaults.extend(
                [
                    ModelEntry(
                        key="DECONTEXT_MODEL",
                        model_name="google/flan-t5-base",
                        task_type="seq2seq_generation",
                        owner_component="Decontextualizer",
                        loader="auto_model_seq2seq",
                        device_policy=DevicePolicy.PREFER_GPU,
                        required=False,
                        estimated_memory_mb=950,
                    ),
                    ModelEntry(
                        key="DECONTEXT_TOKENIZER",
                        model_name="google/flan-t5-base",
                        task_type="tokenizer",
                        owner_component="Decontextualizer",
                        loader="auto_tokenizer",
                        device_policy=DevicePolicy.CPU_ONLY,
                        required=False,
                        estimated_memory_mb=10,
                    ),
                    ModelEntry(
                        key="DECONTEXT_QG_MODEL",
                        model_name=os.environ.get(
                            "NLP_QG_MODEL", "Salesforce/mixqg-base"
                        ),
                        task_type="seq2seq_generation",
                        owner_component="Decontextualizer",
                        loader="auto_model_seq2seq",
                        device_policy=DevicePolicy.PREFER_GPU,
                        required=False,
                        estimated_memory_mb=900,
                    ),
                    ModelEntry(
                        key="DECONTEXT_QG_TOKENIZER",
                        model_name=os.environ.get(
                            "NLP_QG_MODEL", "Salesforce/mixqg-base"
                        ),
                        task_type="tokenizer",
                        owner_component="Decontextualizer",
                        loader="auto_tokenizer",
                        device_policy=DevicePolicy.CPU_ONLY,
                        required=False,
                        estimated_memory_mb=10,
                    ),
                    ModelEntry(
                        key="DECONTEXT_QA_MODEL",
                        model_name=os.environ.get(
                            "NLP_QA_MODEL", "deepset/roberta-base-squad2"
                        ),
                        task_type="question_answering",
                        owner_component="Decontextualizer",
                        loader="auto_model_qa",
                        device_policy=DevicePolicy.PREFER_GPU,
                        required=False,
                        estimated_memory_mb=500,
                    ),
                    ModelEntry(
                        key="DECONTEXT_QA_TOKENIZER",
                        model_name=os.environ.get(
                            "NLP_QA_MODEL", "deepset/roberta-base-squad2"
                        ),
                        task_type="tokenizer",
                        owner_component="Decontextualizer",
                        loader="auto_tokenizer",
                        device_policy=DevicePolicy.CPU_ONLY,
                        required=False,
                        estimated_memory_mb=10,
                    ),
                ]
            )
        else:
            logger.info(
                "ModelManager: skipping decontext model registration because ENABLE_DECONTEXTUALIZATION is false."
            )
        for entry in defaults:
            self.register(entry)

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load(self, key: str) -> None:
        """Load a single model by key; transition: UNLOADED -> LOADING -> READY/ERROR.

        Clears the threading event before loading so concurrent get() calls block.
        Sets the event after loading (whether success or error) so blocked get()
        calls proceed. Catches all exceptions and stores them in entry.error.

        Args:
            key: Model key to load (must be registered).

        Raises:
            ModelNotFoundError: If key is not registered.
        """
        if key not in self._registry:
            raise ModelNotFoundError(f"Model key '{key}' is not registered.")

        entry = self._registry[key]
        entry.state = ModelState.LOADING
        # Clear the event so get() will block until loading completes.
        self._events[key].clear()

        try:
            instance = self._load_model(entry)
            entry.instance = instance
            entry.state = ModelState.READY
            logger.info(
                "ModelManager: '%s' loaded successfully (%s).", key, entry.loader
            )
        except Exception as exc:
            entry.error = exc
            entry.state = ModelState.ERROR
            logger.error("ModelManager: Failed to load '%s': %s", key, exc)
        finally:
            # Always set the event so blocked get() calls can proceed.
            self._events[key].set()

    def load_all(self, keys: Optional[List[str]] = None) -> None:
        """Load all (or specified) registered models sequentially.

        Parallel loading was removed: transformers >= 4.38 uses init_empty_weights()
        (meta device) during pipeline() construction. This meta-device state is
        global per process and bleeds across threads, leaving model weights on the
        meta device at inference time even when loading succeeds. Sequential loading
        eliminates this with no correctness risk.

        In dummy_mode, skips loading entirely (no-op).

        Args:
            keys: Specific model keys to load. If None, loads all registered keys.
                  Only loads models not already in READY state.
        """
        if self._dummy_mode:
            logger.info("ModelManager: dummy mode — skipping all model loading.")
            return

        all_entries = [self._registry[k] for k in (keys or list(self._registry.keys()))]
        # Skip models that are already loaded successfully.
        entries = [e for e in all_entries if e.state != ModelState.READY]

        # Load smallest first to surface OOM failures early on memory-limited devices.
        for entry in sorted(entries, key=lambda e: e.estimated_memory_mb):
            self.load(entry.key)

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def get(self, key: str) -> Any:
        """Retrieve loaded model instance by key; blocks if currently loading.

        If the model is in LOADING state, waits on the threading event until the
        state transitions to READY or ERROR. Respects the caching strategy by
        returning the same instance object for repeated calls.

        Args:
            key: Registered model key.

        Returns:
            The loaded model instance.

        Raises:
            ModelNotFoundError: If key is not registered.
            ModelLoadError: If model is in ERROR state (load failed).
            ModelNotReadyError: If model is UNLOADED (never loaded).
        """
        if key not in self._registry:
            raise ModelNotFoundError(f"Model key '{key}' is not registered.")

        entry = self._registry[key]

        if entry.state == ModelState.LOADING:
            logger.debug("ModelManager: '%s' is loading — blocking until ready.", key)
            self._events[key].wait()

        if entry.state == ModelState.READY:
            return entry.instance

        if entry.state == ModelState.ERROR:
            raise ModelLoadError(
                f"Model '{key}' failed to load: {entry.error}"
            ) from entry.error

        # UNLOADED
        raise ModelNotReadyError(
            f"Model '{key}' has not been loaded yet. Call load() or load_all() first."
        )

    def get_state(self, key: str) -> ModelState:
        """Get the current ModelState (UNLOADED, LOADING, READY, ERROR) for a key.

        Args:
            key: Registered model key.

        Returns:
            The ModelState enum value.

        Raises:
            ModelNotFoundError: If key is not registered.
        """
        if key not in self._registry:
            raise ModelNotFoundError(f"Model key '{key}' is not registered.")
        return self._registry[key].state

    # ------------------------------------------------------------------
    # Health / Cleanup
    # ------------------------------------------------------------------

    def health_check(self) -> Dict[str, str]:
        """Get health status of all registered models.

        Returns:
            Dict mapping model keys to their ModelState.value (unloaded, loading,
            ready, error).
        """
        return {key: entry.state.value for key, entry in self._registry.items()}

    def unload(self, key: str) -> None:
        """Unload a single model and free its instance reference from cache.

        Clears the model's threading event so subsequent get() calls raise
        ModelNotReadyError until load() is called again.

        Args:
            key: Registered model key.

        Raises:
            ModelNotFoundError: If key is not registered.
        """
        if key not in self._registry:
            raise ModelNotFoundError(f"Model key '{key}' is not registered.")
        entry = self._registry[key]
        entry.instance = None
        entry.state = ModelState.UNLOADED
        self._events[key].clear()
        logger.info("ModelManager: '%s' unloaded.", key)

    def unload_all(self) -> None:
        """Unload all registered models and free their cached instances."""
        for key in list(self._registry.keys()):
            self.unload(key)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_device(self, policy: DevicePolicy) -> str:
        """Resolve device placement for a model based on its DevicePolicy.

        Device selection logic:
            - DevicePolicy.CPU_ONLY: Always return "cpu" regardless of instance device.
            - DevicePolicy.PREFER_GPU: Return instance device ("cuda" or "cpu").
            - DevicePolicy.GPU_REQUIRED: Return instance device (caller enforces GPU).

        Args:
            policy: The model's DevicePolicy enum.

        Returns:
            Device string: "cpu" or "cuda".
        """

    def _validate_hf_cache(self, model_name: str) -> None:
        """Validate HuggingFace cache for corrupted files; delegate to static method.

        Args:
            model_name: HuggingFace model identifier (e.g., "dslim/bert-base-NER").
        """
        ModelManager.validate_hf_cache(model_name)

    @staticmethod
    def validate_hf_cache(model_name: str) -> None:
        """Detect and clean corrupted files in HuggingFace cache.

        Scans the HuggingFace cache directory for:
            - Empty JSON files (incomplete downloads).
            - JSON files with invalid UTF-8 or unparseable JSON.
            - Broken symlinks in snapshot directories.

        Corrupted files are removed so from_pretrained() will re-download cleanly.
        Can be called as a standalone utility without a ModelManager instance.

        Args:
            model_name: HuggingFace model identifier (e.g., "dslim/bert-base-NER").
                       Converted to safe cache path: models--<org>--<name>.
        """
        hf_home = os.environ.get("HF_HOME") or os.environ.get(
            "TRANSFORMERS_CACHE",
            os.path.join(os.path.expanduser("~"), ".cache", "huggingface"),
        )
        hub_cache = Path(hf_home) / "hub"
        if not hub_cache.is_dir():
            return

        # HF cache stores models under models--<org>--<name>
        safe_name = model_name.replace("/", "--")
        model_dir = hub_cache / f"models--{safe_name}"
        if not model_dir.is_dir():
            return

        # Walk snapshot directories looking for corrupt JSON/config files.
        corrupt_found = False
        for json_file in model_dir.rglob("*.json"):
            if json_file.stat().st_size == 0:
                logger.warning(
                    "ModelManager: Removing empty cache file %s (corrupted download).",
                    json_file,
                )
                json_file.unlink()
                corrupt_found = True
                continue
            # Validate that JSON files are parseable.
            try:
                with open(json_file, "r") as f:
                    json.load(f)
            except (json.JSONDecodeError, UnicodeDecodeError):
                logger.warning(
                    "ModelManager: Removing corrupt cache file %s.",
                    json_file,
                )
                json_file.unlink()
                corrupt_found = True

        if corrupt_found:
            # Also remove the corresponding blob files that reference the
            # deleted snapshots, if any refs point to missing files.
            refs_dir = model_dir / "refs"
            if refs_dir.is_dir():
                for ref_file in refs_dir.iterdir():
                    if ref_file.is_file():
                        ref_hash = ref_file.read_text().strip()
                        snapshot_dir = model_dir / "snapshots" / ref_hash
                        if snapshot_dir.is_dir():
                            # Check if this snapshot has broken symlinks
                            for f in snapshot_dir.iterdir():
                                if f.is_symlink() and not f.exists():
                                    logger.warning(
                                        "ModelManager: Removing broken symlink %s.",
                                        f,
                                    )
                                    f.unlink()

            logger.info(
                "ModelManager: Cleaned corrupted cache for '%s'. "
                "Model will be re-downloaded on next load.",
                model_name,
            )

    def _resolve_hf_task(self, entry: ModelEntry) -> str:
        """Map a ModelEntry's task_type to a HuggingFace pipeline task string.

        Args:
            entry: ModelEntry with task_type field.

        Returns:
            HuggingFace task string (e.g., "token-classification" for NER).
        """
        _TASK_MAP = {
            "zero_shot_classification": "zero-shot-classification",
            "token_classification": "token-classification",
            "text_classification": "text-classification",
            "sentiment_analysis": "sentiment-analysis",
        }
        return _TASK_MAP.get(entry.task_type, entry.task_type)

    def _load_model(self, entry: ModelEntry) -> Any:
        """Load a model instance by dispatching to the appropriate loader.

        Device placement:
            - Resolves device per model's DevicePolicy (CPU_ONLY vs PREFER_GPU).
            - GPU models (device == "cuda") are loaded with float16 precision to
              reduce memory footprint.
            - For transformers pipelines: device=0 for cuda (GPU), device=-1 for CPU.

        Loader dispatch:
            - "spacy": Load spacy NLP model (CPU_ONLY).
            - "sentence_transformer": SentenceTransformer with device placement.
            - "transformers_pipeline": HuggingFace pipeline (auto-dtype on GPU).
            - "auto_model_seq2seq": Seq2seq model (T5, etc).
            - "auto_model_qa": Question-answering model.
            - "auto_tokenizer": Tokenizer only (no device).

        Args:
            entry: ModelEntry specifying loader, model_name, device_policy, etc.

        Returns:
            Loaded model instance (type depends on loader).

        Raises:
            ValueError: If loader type is unknown.
            Exception: Any exception from underlying model libraries (stored in entry.error).
        """
        # Validate HF cache before loading to detect corrupted downloads.
        if entry.loader != "spacy":
            self._validate_hf_cache(entry.model_name)

        device = self._resolve_device(entry.device_policy)

        if entry.loader == "spacy":
            import spacy

            return spacy.load(entry.model_name, **entry.loader_kwargs)

        elif entry.loader == "sentence_transformer":
            from sentence_transformers import SentenceTransformer

            model = SentenceTransformer(entry.model_name, device=device)
            if device == "cuda":
                model.half()
            return model

        elif entry.loader == "transformers_pipeline":
            import torch as _torch
            from transformers import pipeline

            hf_device = 0 if device == "cuda" else -1
            task = self._resolve_hf_task(entry)
            kwargs = dict(entry.loader_kwargs)
            if device == "cuda":
                kwargs["dtype"] = _torch.float16
            return pipeline(task, model=entry.model_name, device=hf_device, **kwargs)

        elif entry.loader == "auto_model_seq2seq":
            import torch as _torch
            from transformers import AutoModelForSeq2SeqLM

            torch_dtype = None
            if device == "cuda":
                # fp16 is only safe/beneficial on CUDA in this project.
                import torch

                torch_dtype = torch.float16

            model = AutoModelForSeq2SeqLM.from_pretrained(
                entry.model_name,
                torch_dtype=torch_dtype,
                low_cpu_mem_usage=False,
            )
            model.to(device)
            model.eval()
            return model

        elif entry.loader == "auto_model_qa":
            import torch as _torch
            from transformers import AutoModelForQuestionAnswering

            torch_dtype = None
            if device == "cuda":
                import torch

                torch_dtype = torch.float16

            model = AutoModelForQuestionAnswering.from_pretrained(
                entry.model_name,
                torch_dtype=torch_dtype,
                low_cpu_mem_usage=False,
            )
            model.to(device)
            model.eval()
            return model

        elif entry.loader == "auto_tokenizer":
            from transformers import AutoTokenizer

            return AutoTokenizer.from_pretrained(entry.model_name)

        else:
            raise ValueError(
                f"Unknown loader type '{entry.loader}' for model key '{entry.key}'."
            )
