from datetime import datetime
import json
import uuid
from typing import Any, Dict, Optional, List

from common.service.service_template import ServiceTemplate
from common.models.api.redis_models import Message, StreamMessage
from common.redis_client.publisher import RedisPublisher
from microservices.retrieval_layer.processor import process_nlp_message
from microservices.retrieval_layer.config import (
    USER_OUTPUT_STREAM,
    FAILURE_OUTPUT_STREAM,
    DUMMY_NLP_MODE,
    DUMMY_SEED_MODE,
)
from microservices.retrieval_layer.retrieval.pipeline import retrieve_candidate_claims
from microservices.retrieval_layer.db.session import get_db_session
from microservices.retrieval_layer.storage.crud import (
    get_or_create_article,
    create_claim_and_link_entities,
)
from logging import error, getLogger
from pydantic import ValidationError

EMBEDDING_DIM = 768
_DUMMY_CORPUS_SEEDED = False
_DUMMY_BASE_EMBEDDING = [0.05] * EMBEDDING_DIM

# Define 3 distinct dummy article embeddings
_DUMMY_EMBEDDINGS = {
    "article_1": [0.1] * EMBEDDING_DIM,  # Government/Taxes
    "article_2": [0.3] * EMBEDDING_DIM,  # Climate
    "article_3": [0.5] * EMBEDDING_DIM,  # Healthcare
}


def _create_similar_embedding(base_pattern: float, noise_level: float = 0.05) -> List[float]:
    """Create an embedding similar to a base pattern with slight variation."""
    return [base_pattern + (noise_level if i % 2 == 0 else -noise_level) for i in range(EMBEDDING_DIM)]


def _extract_sentiment(payload: Any) -> Optional[Dict[str, Any]]:
    bias_profile = getattr(payload, "bias_profile", None)
    if not bias_profile:
        return None

    scores = getattr(bias_profile, "scores", None)
    bias_score = None
    if isinstance(scores, dict) and scores:
        bias_score = max(scores.values())

    return {
        "bias_category": getattr(bias_profile, "political_bias", None),
        "bias_score": bias_score,
        "bias_analysis_confidence": getattr(bias_profile, "confidence", None),
        "sentiment_category": getattr(bias_profile, "emotional_tone", None),
        "sentiment_analysis_confidence": getattr(bias_profile, "confidence", None),
    }


def _normalize_claims(claims: List[Any]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for c in claims or []:
        if isinstance(c, dict):
            normalized.append(
                {
                    "original_sentence": c.get("original_sentence") or c.get("contextualised_claim"),
                    "decontextualised_claim": c.get("decontextualised_claim"),
                    "decontextualised_embedding": c.get("decontextualised_embedding"),
                    "centrality_score": c.get("centrality_score"),
                    "entities": c.get("entities", []),
                }
            )
            continue

        entities = []
        for ent in getattr(c, "NER_entities", []) or []:
            entities.append(
                {
                    "name": getattr(ent, "entity_text", None),
                    "type": getattr(ent, "type_of_entity", None),
                }
            )

        normalized.append(
            {
                "original_sentence": getattr(c, "contextualised_claim_text", None),
                "decontextualised_claim": getattr(c, "decontextualised_claim_text", None),
                "decontextualised_embedding": getattr(c, "decontextualised_claim_embedding", None),
                "centrality_score": None,
                "entities": entities,
            }
        )

    return normalized


def _build_dummy_message(article_url: str, claim_text: str) -> Dict[str, Any]:
    return {
        "article": {
            "url": article_url,
            "title": "Dummy Article",
            "text": "A short dummy article about taxes and policy.",
            "html": "<p>Dummy article about taxes and policy.</p>",
            "publishedAt": "2026-02-23T00:00:00",
            "outlet_name": "Dummy Outlet",
        },
        "claims": [
            {
                "original_sentence": claim_text,
                "decontextualised_claim": claim_text,
                "decontextualised_embedding": _DUMMY_BASE_EMBEDDING,
                "centrality_score": 0.95,
                "entities": [
                    {"name": "Government", "type": "ORG"},
                    {"name": "taxes", "type": "TOPIC"},
                ],
            }
        ],
    }


def _seed_dummy_corpus() -> None:
    global _DUMMY_CORPUS_SEEDED
    if _DUMMY_CORPUS_SEEDED:
        return

    db = get_db_session()
    try:
        # Define 3 dummy articles with different topics and embeddings
        articles_data = [
            {
                "url": "https://dummy.local/article/seed-1",
                "title": "Dummy Article 1: Government Policy",
                "text": "Article about government taxation policies and economic impact.",
                "outlet_name": "Dummy Outlet 1",
                "embedding": _DUMMY_EMBEDDINGS["article_1"],
                "claims": [
                    ("Government raised taxes", "Government raised taxes", 0.0),
                    ("Tax increases impact citizens", "Tax increases impact citizens", 0.01),
                    ("Revenue from taxes increased", "Revenue from taxes increased", 0.02),
                ]
            },
            {
                "url": "https://dummy.local/article/seed-2",
                "title": "Dummy Article 2: Climate Change",
                "text": "Article about climate change impacts and environmental policies.",
                "outlet_name": "Dummy Outlet 2",
                "embedding": _DUMMY_EMBEDDINGS["article_2"],
                "claims": [
                    ("Climate is changing rapidly", "Climate is changing rapidly due to human activity", 0.0),
                    ("Carbon emissions are rising", "Carbon emissions continue to rise globally", 0.01),
                    ("Green energy is critical", "Renewable energy solutions are critical for sustainability", 0.02),
                ]
            },
            {
                "url": "https://dummy.local/article/seed-3",
                "title": "Dummy Article 3: Healthcare Reform",
                "text": "Article about healthcare system improvements and medical innovations.",
                "outlet_name": "Dummy Outlet 3",
                "embedding": _DUMMY_EMBEDDINGS["article_3"],
                "claims": [
                    ("Healthcare costs are rising", "Healthcare costs continue to rise across the nation", 0.0),
                    ("Medications are unaffordable", "Prescription medications are becoming increasingly unaffordable", 0.01),
                    ("Medical technology advancing", "New medical technology is advancing patient care significantly", 0.02),
                ]
            },
        ]

        for article_data in articles_data:
            article = get_or_create_article(
                db,
                {
                    "url": article_data["url"],
                    "title": article_data["title"],
                    "text": article_data["text"],
                    "html": f"<p>{article_data['text']}</p>",
                    "publishedAt": "2026-02-23T00:00:00",
                    "outlet_name": article_data["outlet_name"],
                },
            )
            
            # Create 3 claims for each article with slightly different embeddings
            base_value = article_data["embedding"][0]
            for original_sentence, decontextualised_claim, noise_offset in article_data["claims"]:
                # Create unique embedding for each claim by adding a small offset
                claim_embedding = [base_value + noise_offset] * EMBEDDING_DIM
                
                create_claim_and_link_entities(
                    db,
                    {
                        "original_sentence": original_sentence,
                        "decontextualised_claim": decontextualised_claim,
                        "decontextualised_embedding": claim_embedding,
                        "centrality_score": 0.9,
                        "entities": [
                            {"name": "General", "type": "TOPIC"},
                        ],
                    },
                    article_obj=article,
                )

        db.commit()
        _DUMMY_CORPUS_SEEDED = True
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

def _create_synthetic_user_claims() -> List[Dict[str, Any]]:
    """
    Create 3 synthetic claims for user articles, each with embedding directly matching a dummy article.
    This ensures retrieval matches against each of the 3 dummy article topics.
    """
    claims = [
        {
            "original_sentence": "Government policy affects citizens",
            "decontextualised_claim": "Government policy affects citizens",
            "decontextualised_embedding": _DUMMY_EMBEDDINGS["article_1"],  # Direct match to Article 1
            "centrality_score": 0.85,
            "entities": [{"name": "Government", "type": "ORG"}],
        },
        {
            "original_sentence": "Environmental changes are occurring",
            "decontextualised_claim": "Environmental changes are occurring",
            "decontextualised_embedding": _DUMMY_EMBEDDINGS["article_2"],  # Direct match to Article 2
            "centrality_score": 0.87,
            "entities": [{"name": "Environment", "type": "TOPIC"}],
        },
        {
            "original_sentence": "Healthcare systems are evolving",
            "decontextualised_claim": "Healthcare systems are evolving",
            "decontextualised_embedding": _DUMMY_EMBEDDINGS["article_3"],  # Direct match to Article 3
            "centrality_score": 0.86,
            "entities": [{"name": "Healthcare", "type": "TOPIC"}],
        },
    ]
    return claims


logger = getLogger(__name__)


class RetrievalService(ServiceTemplate):
    def __init__(self, config):
        super().__init__(config)
        # self.config = config
        self.user_publisher = RedisPublisher(USER_OUTPUT_STREAM)
        self.failure_publisher = RedisPublisher(FAILURE_OUTPUT_STREAM)
        
        # Seed dummy corpus once at startup if in dummy seed mode
        if DUMMY_SEED_MODE:
            logger.info("DUMMY_SEED_MODE enabled - seeding dummy corpus at startup")
            _seed_dummy_corpus()
            logger.info("Dummy corpus seeded successfully")

    # -------------------------------
    # 1. Parse Redis message
    # -------------------------------
    def _parse_message(self, raw_msg: Dict[str, Any]) -> Optional[StreamMessage]:
        msg_data = raw_msg.get("data", {})

        try:
            # First, check if the message has the new format (wrapped in "payload")
            if "payload" in msg_data and "header" not in msg_data:
                # New format: everything is JSON-stringified inside "payload"
                inner_data = json.loads(msg_data["payload"])
                reconstructed = {
                    "header": inner_data.get("header", {}),
                    "payload": inner_data.get("payload", {}),
                    "stage_timestamps": inner_data.get("stage_timestamps", []),
                }
            elif "header" in msg_data:
                # Old format: header/payload/stage_timestamps are separate fields, already JSON strings
                reconstructed = {
                    "header": json.loads(msg_data["header"]) if isinstance(msg_data["header"], str) else msg_data["header"],
                    "payload": json.loads(msg_data.get("payload", "{}")) if isinstance(msg_data.get("payload", "{}"), str) else msg_data.get("payload", {}),
                    "stage_timestamps": json.loads(msg_data.get("stage_timestamps", "[]")) if isinstance(msg_data.get("stage_timestamps", "[]"), str) else msg_data.get("stage_timestamps", []),
                }
            else:
                # Fallback: treat entire msg_data as payload
                reconstructed = {
                    "header": {},
                    "payload": msg_data,
                    "stage_timestamps": [],
                }

            hdr = reconstructed["header"]
            hdr.setdefault("uid", str(uuid.uuid4()))
            hdr.setdefault("type", "user")
            hdr.setdefault("status", "pending")
            hdr.setdefault("created_at", datetime.utcnow().isoformat())

            parsed = Message.model_validate(reconstructed)

            return StreamMessage(
                stream=raw_msg["stream"],
                redis_id=raw_msg["redis_message_id"],
                data=parsed,
                priority=0,
            )

        except (ValidationError, json.JSONDecodeError) as e:
            logger.exception("Failed to parse retrieval message")
            self._handle_failure(raw_msg, e)
            return None

    # -------------------------------
    # 2. Business logic
    # -------------------------------
    def _process_message(self, message: StreamMessage) -> StreamMessage:
        payload = message.data.payload

        if DUMMY_NLP_MODE:
            message_dict = _build_dummy_message(
                article_url=f"https://dummy.local/article/user-{message.data.header.uid}",
                claim_text="Government increased taxes",
            )
        else:
            sentiment = _extract_sentiment(payload)
            claims = _normalize_claims(payload.claims_in_article)
            message_dict = {
                "article": {
                    "url": payload.article_url,
                    "title": payload.title,
                    "text": payload.parsed_text,
                    "html": payload.raw_html,
                    "publishedAt": payload.publish_date,
                    "outlet_name": payload.news_outlet,
                    "sentiment": sentiment,
                },
                "claims": claims,
            }

        # For user articles, generate 3 synthetic claims matching dummy articles (for demo/testing)
        if message.data.header.type == "user":
            message_dict["claims"] = _create_synthetic_user_claims()
            logger.info(
                "Generated 3 synthetic claims for user article uid=%s",
                message.data.header.uid,
            )

        logger.info(
            "Retrieval received message uid=%s type=%s url=%s claims=%s",
            message.data.header.uid,
            message.data.header.type,
            message_dict.get("article", {}).get("url"),
            len(message_dict.get("claims", []) or []),
        )

        result = process_nlp_message(message_dict)
        logger.info(
            "DB write result article_id=%s claim_ids=%s",
            result.get("created_article_id"),
            result.get("created_claim_ids"),
        )

        retrieval_output = None

        has_claims = bool(message_dict.get("claims"))
        if message.data.header.type == "user" and has_claims:
            # Run retrieval on all claims for user articles
            db = get_db_session()
            try:
                top_k = 3 if DUMMY_NLP_MODE else 5
                all_retrieval_results = []
                
                for claim in message_dict["claims"]:
                    retrieval_results = retrieve_candidate_claims(
                        db=db,
                        claim_text=claim["decontextualised_claim"],
                        claim_embedding=claim["decontextualised_embedding"],
                        entities=[e["name"] for e in claim.get("entities", [])],
                        top_k=top_k,
                        run_nli=not DUMMY_NLP_MODE,
                    )
                    
                    # Store results with claim text for reference
                    if DUMMY_NLP_MODE:
                        # When run_nli=False, only (claim, score) is returned
                        claim_results = [
                            {
                                "claim_id": c["id"],
                                "claim_text": c["decontextualised_claim"],
                                "similarity": float(score),
                                "relation": "unknown",
                                "confidence": 0.0,
                                "query_claim": claim["decontextualised_claim"],
                            }
                            for c, score in retrieval_results
                        ]
                    else:
                        # When run_nli=True, (claim, score, label, confidence) is returned
                        claim_results = [
                            {
                                "claim_id": c["id"],
                                "claim_text": c["decontextualised_claim"],
                                "similarity": float(score),
                                "relation": label,
                                "confidence": confidence,
                                "query_claim": claim["decontextualised_claim"],
                            }
                            for c, score, label, confidence in retrieval_results
                        ]
                    
                    all_retrieval_results.extend(claim_results)
                
                retrieval_output = all_retrieval_results
                
                if DUMMY_NLP_MODE and result.get("created_article_id"):
                    retrieval_output = [
                        item for item in retrieval_output
                        if item["claim_id"] not in (result.get("created_claim_ids") or [])
                    ][:top_k]
            finally:
                db.close()

            logger.info(
                "Retrieval matches uid=%s count=%s",
                message.data.header.uid,
                0 if retrieval_output is None else len(retrieval_output),
            )
        
        
        # publish success
        self.user_publisher.publish_one({
        "job_uid": message.data.header.uid,
        "status": "completed",
        "retrieval_result": {
            **result,
            "matches": retrieval_output,
            }
        })

        return message

    # -------------------------------
    # 3. Failure handling
    # -------------------------------
    def _handle_failure(self, raw_msg: Dict[str, Any], error: Exception):
        logger.error("Routing message to failure stream")

        self.failure_publisher.publish_one(
            {
                "error": str(error),
                "raw_message": raw_msg,
                "failed_at": datetime.utcnow().isoformat(),
            }
        )
