from transformers import pipeline

_nli = None

def get_nli():
    global _nli
    if _nli is None:
        _nli = pipeline(
            "text-classification",
            model="typeform/distilbert-base-uncased-mnli",
            device=-1,
        )
    return _nli

LABEL_MAP = {
    "ENTAILMENT": "support",
    "CONTRADICTION": "contradict",
    "NEUTRAL": "irrelevant",
}

def classify_claim_relation(user_claim: str, candidate_claim: str):
    nli = get_nli()
    # print("DEBUG NLI INPUT:", {"text": candidate_claim, "text_pair": user_claim})
    result = nli(
        {
            "text": candidate_claim,
            "text_pair": user_claim
        },
        truncation=True
    )

    return LABEL_MAP[result["label"]], float(result["score"])
