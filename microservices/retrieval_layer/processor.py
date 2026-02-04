from microservices.retrieval_layer.crud import get_or_create_article, create_claim_and_link_entities
from microservices.retrieval_layer.db.session import get_db_session
from typing import Dict, Any


def process_nlp_message(message: Dict[str, Any]) -> Dict[str, Any]:
    """
    message: dict produced by NLP pipeline. expected keys:
      - article: {url, title, text, html, publishedAt, outlet_name, sentiment?}
      - claims: [ { original_sentence, decontextualised_claim, decontextualised_embedding, centrality_score, entities: [{name,type}] }, ... ]
    Returns: summary dict with created ids.
    """
    db = get_db_session()
    result = {"created_article_id": None, "created_claim_ids": []}
    try:
        article_d = message.get("article", {})
        article_obj = get_or_create_article(db, article_d)
        result["created_article_id"] = article_obj.id

        claims = message.get("claims", []) or []
        for c in claims:
            claim_obj = create_claim_and_link_entities(db, claim_d=c, article_obj=article_obj)
            result["created_claim_ids"].append(claim_obj.id)

        db.commit()
        return result
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
