from typing import List, Any
from pydantic import ValidationError
import json
from common.models.api.redis_models import Message, MessagePayload, StreamMessage

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
    required = ["news_outlet", "article_url", "title"]
    validate_fields(message.payload, required, "Ingestor")


def validate_after_webscraper(stream_message: StreamMessage) -> None:
    message = stream_message.data
    required = [
        "news_outlet",
        "article_url",
        "publish_date",
        "author",
        "parsed_text",   
        "raw_html"      
    ]
    validate_fields(message.payload, required, "WebScraper")


def validate_after_nlp(stream_message: StreamMessage) -> None:
    """
    Validate that NLP stage has produced well-formed claims, entities, and bias profile.
    Raises ValueError if any required field is missing or malformed.
    """
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


def validate_after_retrieval(stream_message: StreamMessage) -> None:
    message = stream_message.data
    required = [
        "save_data_result",
        "save_job_result",
        "matches",
        "related_articles"
    ]
    validate_fields(message.payload, required, "Retrieval")
    

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


def get_pretty_print_stream_message(stream_message: StreamMessage, snippet_len: int = 200) -> str:
    """
    Pretty prints a StreamMessage object for inspection.
    Uses Pydantic's model_dump for safe serialization.
    Long text/html fields are truncated to a snippet.
    """
    msg_dict = stream_message.data.model_dump()

    # Add stream metadata
    msg_dict["Stream"] = stream_message.stream
    msg_dict["RedisID"] = stream_message.redis_id
    msg_dict["Priority"] = stream_message.priority

    # Truncate long text/html fields
    if msg_dict["payload"].get("parsed_text"):
        msg_dict["payload"]["parsed_text_snippet"] = (
            msg_dict["payload"]["parsed_text"][:snippet_len] + "..."
            if len(msg_dict["payload"]["parsed_text"]) > snippet_len
            else msg_dict["payload"]["parsed_text"]
        )
    if msg_dict["payload"].get("raw_html"):
        msg_dict["payload"]["raw_html_snippet"] = (
            msg_dict["payload"]["raw_html"][:snippet_len] + "..."
            if len(msg_dict["payload"]["raw_html"]) > snippet_len
            else msg_dict["payload"]["raw_html"]
        )

    return json.dumps(msg_dict, indent=4, ensure_ascii=False)
