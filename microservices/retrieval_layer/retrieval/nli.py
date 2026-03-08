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
        )
    return _nli

LABEL_MAP = {
    "ENTAILMENT": "support",
    "CONTRADICTION": "contradict",
    "NEUTRAL": "irrelevant",
}

def classify_claim_relation(user_claim: str, candidate_claim: str):
    nli = get_nli()
    result = nli(
        {
            "text": candidate_claim,
            "text_pair": user_claim
        },
        truncation=True
    )[0]

    return LABEL_MAP[result["label"]], float(result["score"])
