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
            return_all_scores=True
        )
        
    return _nli

LABEL_MAP = {
    "LABEL_0": "support",      # 0 = ENTAILMENT
    "LABEL_1": "irrelevant",   # 1 = NEUTRAL  
    "LABEL_2": "contradict",   # 2 = CONTRADICTION
}

def classify_claim_relation(user_claim: str, candidate_claim: str):
    nli = get_nli()
    #             premise            hypothesis
    text_pair = f"{user_claim} [SEP] {candidate_claim}"
    result = nli(
        text_pair,
        truncation=True
    )[0]

    label = result["label"]
    score = result["score"]
    
    return LABEL_MAP[label], float(score)
