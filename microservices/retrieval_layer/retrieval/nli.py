from transformers import pipeline
import torch

_nli = None

def get_nli():
    global _nli
    if _nli is None:
        _nli = pipeline(
            "text-classification",
            model="typeform/distilbert-base-uncased-mnli",
            device=0 if torch.cuda.is_available() else -1,  
            # return_all_scores=True
        )
        
    return _nli

LABEL_ALIASES = {
    # Common textual labels
    "entailment": "support",
    "neutral": "irrelevant",
    "contradiction": "contradict",
    # Some checkpoints use this spelling
    "contradict": "contradict",
    # Fallback label IDs (ordering can differ by checkpoint)
    # Keep common MNLI default here; textual labels are preferred when present.
    "label_0": "entailment",
    "label_1": "neutral",
    "label_2": "contradiction",
}


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
    #             premise            hypothesis
    text_pair = f"{user_claim} [SEP] {candidate_claim}"
    raw_result = nli(
        text_pair,
        truncation=True
    )

    # Handle output shape differences across transformers versions:
    # - [[{label, score}, ...]]
    # - [{label, score}, ...]
    # - {label, score}
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
