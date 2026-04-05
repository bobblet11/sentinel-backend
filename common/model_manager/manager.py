import json
import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional

import torch

from common.model_manager.exceptions import (
    ModelLoadError,
    ModelNotFoundError,
    ModelNotReadyError,
)
from common.model_manager.registry import DevicePolicy, ModelEntry, ModelState

logger = logging.getLogger(__name__)


class ModelManager:
    """
    Centralized model lifecycle manager for the NLP pipeline.

    Handles registration, loading (sequential on GPU / parallel on CPU),
    retrieval with blocking during loading, health reporting, and cleanup.
    """

    def __init__(self, device: str = "cpu", dummy_mode: bool = False) -> None:
        self._device = device
        self._dummy_mode = dummy_mode
        self._registry: Dict[str, ModelEntry] = {}
        self._events: Dict[str, threading.Event] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, entry: ModelEntry) -> None:
        """Add a ModelEntry to the internal registry."""
        self._registry[entry.key] = entry
        self._events[entry.key] = threading.Event()

    def register_defaults(self) -> None:
        """Register all default NLP models."""
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
                    "typeform/distilbert-base-uncased-mnli",
                ),
                task_type="zero_shot_classification",
                owner_component="BiasDetector",
                loader="transformers_pipeline",
                device_policy=DevicePolicy.PREFER_GPU,
                required=False,
                estimated_memory_mb=260,
            ),
            ModelEntry(
                key="BIAS_SENTIMENT",
                model_name="cardiffnlp/twitter-roberta-base-sentiment-latest",
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
            # ── Decontextualizer (3 model+tokenizer pairs) ────────────────
            ModelEntry(
                key="DECONTEXT_QG_MODEL",
                model_name=os.environ.get("NLP_QG_MODEL", "Salesforce/mixqg-base"),
                task_type="seq2seq_generation",
                owner_component="Decontextualizer",
                loader="auto_model_seq2seq",
                device_policy=DevicePolicy.PREFER_GPU,
                required=False,
                estimated_memory_mb=900,
            ),
            ModelEntry(
                key="DECONTEXT_QG_TOKENIZER",
                model_name=os.environ.get("NLP_QG_MODEL", "Salesforce/mixqg-base"),
                task_type="tokenizer",
                owner_component="Decontextualizer",
                loader="auto_tokenizer",
                device_policy=DevicePolicy.CPU_ONLY,
                required=False,
                estimated_memory_mb=10,
            ),
            ModelEntry(
                key="DECONTEXT_QA_MODEL",
                model_name=os.environ.get("NLP_QA_MODEL", "deepset/roberta-base-squad2"),
                task_type="question_answering",
                owner_component="Decontextualizer",
                loader="auto_model_qa",
                device_policy=DevicePolicy.PREFER_GPU,
                required=False,
                estimated_memory_mb=500,
            ),
            ModelEntry(
                key="DECONTEXT_QA_TOKENIZER",
                model_name=os.environ.get("NLP_QA_MODEL", "deepset/roberta-base-squad2"),
                task_type="tokenizer",
                owner_component="Decontextualizer",
                loader="auto_tokenizer",
                device_policy=DevicePolicy.CPU_ONLY,
                required=False,
                estimated_memory_mb=10,
            ),
            ModelEntry(
                key="DECONTEXT_MODEL",
                model_name=os.environ.get("NLP_GEN_MODEL", "google/flan-t5-base"),
                task_type="seq2seq_generation",
                owner_component="Decontextualizer",
                loader="auto_model_seq2seq",
                device_policy=DevicePolicy.PREFER_GPU,
                required=False,
                estimated_memory_mb=950,
            ),
            ModelEntry(
                key="DECONTEXT_TOKENIZER",
                model_name=os.environ.get("NLP_GEN_MODEL", "google/flan-t5-base"),
                task_type="tokenizer",
                owner_component="Decontextualizer",
                loader="auto_tokenizer",
                device_policy=DevicePolicy.CPU_ONLY,
                required=False,
                estimated_memory_mb=10,
            ),
        ]
        for entry in defaults:
            self.register(entry)

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load(self, key: str) -> None:
        """Load a single model by key. Transitions: UNLOADED -> LOADING -> READY/ERROR."""
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
            logger.info("ModelManager: '%s' loaded successfully (%s).", key, entry.loader)
        except Exception as exc:
            entry.error = exc
            entry.state = ModelState.ERROR
            logger.error("ModelManager: Failed to load '%s': %s", key, exc)
        finally:
            # Always set the event so blocked get() calls can proceed.
            self._events[key].set()

    def load_all(self, keys: Optional[List[str]] = None) -> None:
        """Load all (or specified) models. Sequential on GPU, parallel on CPU."""
        if self._dummy_mode:
            logger.info("ModelManager: dummy mode — skipping all model loading.")
            return

        entries = [self._registry[k] for k in (keys or list(self._registry.keys()))]

        if self._device == "cuda":
            # Sequential on GPU to avoid OOM — load smallest first.
            for entry in sorted(entries, key=lambda e: e.estimated_memory_mb):
                self.load(entry.key)
        else:
            # Parallel on CPU.
            max_workers = min(4, len(entries)) if entries else 1
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                futures = {pool.submit(self.load, e.key): e.key for e in entries}
                for future in as_completed(futures):
                    key = futures[future]
                    try:
                        future.result()
                    except Exception as exc:
                        logger.error(
                            "ModelManager: Unhandled error loading '%s': %s", key, exc
                        )

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def get(self, key: str) -> Any:
        """
        Return the loaded model instance for key.

        Blocks if the model is currently loading.
        Raises ModelLoadError if in ERROR state.
        Raises ModelNotReadyError if UNLOADED.
        Raises ModelNotFoundError if not registered.
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
        """Return the current ModelState for the given key."""
        if key not in self._registry:
            raise ModelNotFoundError(f"Model key '{key}' is not registered.")
        return self._registry[key].state

    # ------------------------------------------------------------------
    # Health / Cleanup
    # ------------------------------------------------------------------

    def health_check(self) -> Dict[str, str]:
        """Return {key: state.value} for all registered models."""
        return {key: entry.state.value for key, entry in self._registry.items()}

    def unload(self, key: str) -> None:
        """Unload a model and free its instance reference."""
        if key not in self._registry:
            raise ModelNotFoundError(f"Model key '{key}' is not registered.")
        entry = self._registry[key]
        entry.instance = None
        entry.state = ModelState.UNLOADED
        self._events[key].clear()
        logger.info("ModelManager: '%s' unloaded.", key)

    def unload_all(self) -> None:
        """Unload all registered models."""
        for key in list(self._registry.keys()):
            self.unload(key)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_device(self, policy: DevicePolicy) -> str:
        if policy == DevicePolicy.CPU_ONLY:
            return "cpu"
        # PREFER_GPU and GPU_REQUIRED both defer to the instance device.
        return self._device

    def _validate_hf_cache(self, model_name: str) -> None:
        """
        Check the HuggingFace cache for corrupted files (e.g. empty JSON from
        interrupted downloads) and remove them so ``from_pretrained`` will
        re-download cleanly.
        """
        ModelManager.validate_hf_cache(model_name)

    @staticmethod
    def validate_hf_cache(model_name: str) -> None:
        """
        Check the HuggingFace cache for corrupted files (e.g. empty JSON from
        interrupted downloads) and remove them so ``from_pretrained`` will
        re-download cleanly.

        Can be called as a standalone utility without a ModelManager instance:
            ``ModelManager.validate_hf_cache("dslim/bert-base-NER-uncased")``
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
        """Map a ModelEntry's task_type to the HuggingFace pipeline task string."""
        if entry.key in ("BIAS", "BIAS_POLITICAL"):
            if "mnli" in entry.model_name.lower():
                return "zero-shot-classification"
            else:
                entry.loader_kwargs["return_all_scores"] = True
                return "text-classification"

        _TASK_MAP = {
            "zero_shot_classification": "zero-shot-classification",
            "token_classification": "token-classification",
            "text_classification": "text-classification",
            "sentiment_analysis": "sentiment-analysis",
        }
        return _TASK_MAP.get(entry.task_type, entry.task_type)

    def _load_model(self, entry: ModelEntry) -> Any:
        """Dispatch to the appropriate loader based on entry.loader."""
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
            _dtype = _torch.float16 if device == "cuda" else _torch.float32
            task = self._resolve_hf_task(entry)
            return pipeline(
                task, model=entry.model_name, device=hf_device,
                dtype=_dtype, **entry.loader_kwargs,
            )

        elif entry.loader == "auto_model_seq2seq":
            import torch as _torch
            from transformers import AutoModelForSeq2SeqLM

            _dtype = _torch.float16 if device == "cuda" else _torch.float32
            model = AutoModelForSeq2SeqLM.from_pretrained(
                entry.model_name,
                dtype=_dtype,
                low_cpu_mem_usage=False,
            ).to(device)
            return model

        elif entry.loader == "auto_model_qa":
            import torch as _torch
            from transformers import AutoModelForQuestionAnswering

            _dtype = _torch.float16 if device == "cuda" else _torch.float32
            model = AutoModelForQuestionAnswering.from_pretrained(
                entry.model_name,
                dtype=_dtype,
                low_cpu_mem_usage=False,
            ).to(device)
            return model

        elif entry.loader == "auto_tokenizer":
            from transformers import AutoTokenizer

            return AutoTokenizer.from_pretrained(entry.model_name)

        else:
            raise ValueError(
                f"Unknown loader type '{entry.loader}' for model key '{entry.key}'."
            )
