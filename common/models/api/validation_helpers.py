from typing import List, Any
from pydantic import ValidationError
import json
from common.models.api.redis_models import Message, MessagePayload, StreamMessage

import re

HTML_TAG_PATTERN = re.compile(r"<[^>]+>")

def contains_html(text: str) -> bool:
    return bool(text and HTML_TAG_PATTERN.search(text))


# --- Validation helpers ---
def validate_fields(payload: MessagePayload, required_fields: List[str], stage: str) -> None:
    """
    Generic validator to ensure required fields are present in MessagePayload.
    Raises ValueError if any required field is missing or None.
    """
    missing = [f for f in required_fields if getattr(payload, f, None) in (None, "", [])]
    if missing:
        raise ValueError(f"[{stage} Validation Failed] Missing fields: {missing}")


# --- Stage-specific validators ---
def validate_after_ingestor(message: Message) -> None:
    errors = []
    payload = message.payload

    if not payload.news_outlet or not isinstance(payload.news_outlet, str):
        errors.append("Missing or invalid news_outlet")
    if not payload.article_url or not payload.article_url.startswith("http"):
        errors.append("Missing or invalid article_url")
    if not payload.title or len(payload.title.strip()) < 5:
        errors.append("Title too short or missing")

    if errors:
        raise ValueError(f"[Ingestor Validation Failed] {len(errors)} issues:\n - " + "\n - ".join(errors))



def validate_after_webscraper(stream_message: StreamMessage, message: Message = None) -> None:
    if not message and not stream_message:
        raise ValueError("Nothing passed to validate_after_webscraper")
    
    if not message:
        message = stream_message.data

    payload = message.payload
    errors = []

    if not payload.news_outlet:
        errors.append("Missing news_outlet")
    if not payload.article_url or not payload.article_url.startswith("http"):
        errors.append("Invalid article_url")
    if not payload.publish_date:
        errors.append("Missing publish_date")
    if not payload.author:
        errors.append("Missing author")
    if not payload.parsed_text or len(payload.parsed_text) < 50:
        errors.append("Parsed text too short or missing")
    if not payload.raw_html or "<html" not in payload.raw_html.lower():
        errors.append("Raw HTML missing or malformed")
    if contains_html(payload.parsed_text):
        errors.append("Parsed text contains HTML tags")
    if contains_html(payload.title):
        errors.append("Title contains HTML tags")

    if errors:
        raise ValueError(f"[WebScraper Validation Failed] {len(errors)} issues:\n - " + "\n - ".join(errors))



def validate_after_nlp(stream_message: StreamMessage, message: Message=None) -> None:
    """
    Validate that NLP stage has produced well-formed claims, entities, and bias profile.
    Raises ValueError if any required field is missing or malformed.
    """
    if not message and not stream_message:
        raise("Nothing passed to validate_after_webscraper")
    
    if not message:
        message = stream_message.data

    required = [
        "claims_in_article",
        "entities_in_article",
        "bias_profile"
    ]
    validate_fields(message.payload, required, "NLP")

    payload = message.payload
    errors = []

    # --- Claims ---
    for idx, claim in enumerate(payload.claims_in_article or []):
        if claim is None:
            errors.append(f"Claim[{idx}] is None")
            continue
        if claim.confidence is None:
            errors.append(f"Claim[{idx}] missing confidence")
        if not isinstance(claim.source_sentence_indices, list) or not claim.source_sentence_indices:
            errors.append(f"Claim[{idx}] missing source_sentence_indices")
        if not claim.decontextualised_claim_text or not isinstance(claim.decontextualised_claim_text, str):
            errors.append(f"Claim[{idx}] missing decontextualised_claim_text")
        if claim.decontextualised_claim_embedding is None or not isinstance(claim.decontextualised_claim_embedding, list):
            errors.append(f"Claim[{idx}] missing or invalid decontextualised_claim_embedding")

    # --- Entities ---
    for idx, entity in enumerate(payload.entities_in_article or []):
        if entity is None:
            errors.append(f"Entity[{idx}] is None")
            continue
        if not entity.entity_text:
            errors.append(f"Entity[{idx}] missing entity_text")
        if not entity.type_of_entity:
            errors.append(f"Entity[{idx}] missing type_of_entity")
        if entity.start_char is None:
            errors.append(f"Entity[{idx}] missing start_char")
        if entity.end_char is None:
            errors.append(f"Entity[{idx}] missing end_char")

    # --- Bias Profile (renamed class) ---
    bp = payload.bias_profile
    if bp is None:
        errors.append("BiasProfile missing entirely")
    else:
        # Adjusted to match your new dataclass `bias_score`
        if bp.bias_category is None:
            errors.append("BiasProfile missing bias_category")
        if bp.bias_analysis_confidence is None:
            errors.append("BiasProfile missing bias_analysis_confidence")
        if bp.sentiment_category is None:
            errors.append("BiasProfile missing sentiment_category")
        if bp.sentiment_analysis_confidence is None:
            errors.append("BiasProfile missing sentiment_analysis_confidence")

    if errors:
        raise ValueError(f"[NLP Validation Failed] {len(errors)} issues:\n - " + "\n - ".join(errors))


def validate_after_retrieval(stream_message: StreamMessage, message: Message = None) -> None:
    if not message and not stream_message:
        raise ValueError("Nothing passed to validate_after_retrieval")
    if not message:
        message = stream_message.data

    payload = message.payload
    errors = []

    if not payload.save_data_result:
        errors.append("save_data_result missing or not SUCCESS")
    if not payload.save_job_result:
        errors.append("save_job_result missing or not SUCCESS")
    if not isinstance(payload.matches, list) or not payload.matches:
        errors.append("matches missing or not a list")
    if not isinstance(payload.related_articles, list):
        errors.append("related_articles missing or not a list")

    if errors:
        raise ValueError(f"[Retrieval Validation Failed] {len(errors)} issues:\n - " + "\n - ".join(errors))

    

def get_pretty_print_message(message: Message, text_snippet_len: int = 10) -> str:
    """
    Pretty prints a Message object for inspection.
    Uses Pydantic's model_dump for safe serialization.
    Long text/html fields are truncated to a snippet.
    """
    msg_dict = message.model_dump()

    # Truncate long text/html fields
    if msg_dict["payload"].get("parsed_text"):
        msg_dict["payload"]["parsed_text_snippet"] = (
            msg_dict["payload"]["parsed_text"][:text_snippet_len] + "..."
            if len(msg_dict["payload"]["parsed_text"]) > text_snippet_len
            else msg_dict["payload"]["parsed_text"]
        )
    if msg_dict["payload"].get("raw_html"):
        msg_dict["payload"]["raw_html_snippet"] = (
            msg_dict["payload"]["raw_html"][:text_snippet_len] + "..."
            if len(msg_dict["payload"]["raw_html"]) > text_snippet_len
            else msg_dict["payload"]["raw_html"]
        )

    return json.dumps(msg_dict, indent=4, ensure_ascii=False)


def get_pretty_print_stream_message(
    stream_message: StreamMessage,
    snippet_len: int = 50,
    list_snippet_len: int = 3
) -> str:
    """
    Pretty prints a StreamMessage object for inspection.
    Summarizes large lists instead of dumping them.
    """
    msg_dict = stream_message.data.model_dump()

    # Add stream metadata
    msg_dict["Stream"] = stream_message.stream
    msg_dict["RedisID"] = stream_message.redis_id
    msg_dict["Priority"] = stream_message.priority

    payload = msg_dict.get("payload", {})

    # Truncate long text/html fields
    for field in ("parsed_text", "raw_html"):
        if payload.get(field):
            text = str(payload[field])
            payload[field] = text[:snippet_len] + "..." if len(text) > snippet_len else text

    # Helper to summarize lists
    def summarize_list(items, formatter, label):
        total_count = len(items)
        summarized = [formatter(item) for item in items[:list_snippet_len]]
        if total_count > list_snippet_len:
            summarized.append({"note": f"... {total_count - list_snippet_len} more {label} omitted"})
        return summarized, total_count

    # Sentences
    if payload.get("sentences"):
        def fmt_sentence(s):
            return {
                "index": s.get("index"),
                "text_snippet": s.get("text", "")[:snippet_len] + (
                    "..." if len(s.get("text", "")) > snippet_len else ""
                ),
                "score": s.get("score"),
                "is_checkworthy": s.get("is_checkworthy"),
                "entities_count": len(s.get("entities") or []),
            }
        payload["sentences"], payload["number_sentences_in_article"] = summarize_list(
            payload["sentences"], fmt_sentence, "sentences"
        )

    # Claims
    if payload.get("claims_in_article"):
        def fmt_claim(c):
            return {
                "confidence": c.get("confidence"),
                "source_sentence_indices": str(c.get("source_sentence_indices"))[:snippet_len],
                "claim_text_snippet": str(c.get("decontextualised_claim_text"))[:snippet_len],
                "embedding_dims": len(c.get("decontextualised_claim_embedding") or []),
                "entities_count": len(c.get("NER_entities") or []),
            }
        payload["claims_in_article"], payload["number_claims_in_article"] = summarize_list(
            payload["claims_in_article"], fmt_claim, "claims"
        )

    # Entities
    if payload.get("entities_in_article"):
        def fmt_entity(e):
            return {
                "entity_text": e.get("entity_text"),
                "type": e.get("type_of_entity"),
            }
        payload["entities_in_article"], payload["number_entities_in_article"] = summarize_list(
            payload["entities_in_article"], fmt_entity, "entities"
        )

    msg_dict["payload"] = payload
    return json.dumps(msg_dict, indent=4, ensure_ascii=False)
