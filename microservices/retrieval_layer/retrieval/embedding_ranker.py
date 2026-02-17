import numpy as np

def cosine_similarity(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))


def rank_by_embedding_similarity(
    user_embedding,
    candidate_claims,
    top_k=5
):
    """
    candidate_claims: list of Claim ORM objects
                      each has .decontextualised_embedding
    """

    scored = []

    for claim in candidate_claims:
        score = cosine_similarity(
            user_embedding,
            claim.decontextualised_embedding
        )
        scored.append((claim, score))

    scored.sort(key=lambda x: x[1], reverse=True)

    return scored[:top_k]
