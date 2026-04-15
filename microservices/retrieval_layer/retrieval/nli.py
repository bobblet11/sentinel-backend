from transformers import pipeline
import os
import threading
import torch

_thread_local = threading.local()

LABEL_ALIASES = {
    "entailment": "support",
    "neutral": "irrelevant",
    "contradiction": "contradict",
    "contradict": "contradict",
    "label_0": "entailment",
    "label_1": "neutral",
    "label_2": "contradiction",
}

def get_nli():
    nli = getattr(_thread_local, "_nli", None)
    if nli is None:
        use_gpu = os.environ.get("USE_GPU", "false").lower() == "true"
        device_id = 0 if (use_gpu and torch.cuda.is_available()) else -1
        nli = pipeline(
            "text-classification",
            model="typeform/distilbert-base-uncased-mnli",
            device=device_id,
        )
        _thread_local._nli = nli
    return nli

def _normalize_label(raw_label: str) -> str:
    normalized = str(raw_label or "").strip().lower()
    mapped = LABEL_ALIASES.get(normalized, normalized)
    if mapped == "entailment":
        return "support"
    if mapped == "contradiction":
        return "contradict"
    if mapped == "neutral":
        return "irrelevant"
    if mapped in {"support", "contradict", "irrelevant"}:
        return mapped
    return "irrelevant"

def classify_claim_relation(user_claim: str, candidate_claim: str):
    nli = get_nli()
    text_pair = f"{user_claim} [SEP] {candidate_claim}"
    raw_result = nli(text_pair, truncation=True)

    score_items = []
    if isinstance(raw_result, list) and raw_result:
        first = raw_result[0]
        if isinstance(first, list):
            score_items = first
        elif isinstance(first, dict):
            score_items = raw_result
    elif isinstance(raw_result, dict):
        score_items = [raw_result]

    if not score_items:
        return "irrelevant", 0.0

    best_result = max(score_items, key=lambda x: float(x.get("score", 0.0)))
    label = str(best_result.get("label", ""))
    score = float(best_result.get("score", 0.0))

    return _normalize_label(label), score