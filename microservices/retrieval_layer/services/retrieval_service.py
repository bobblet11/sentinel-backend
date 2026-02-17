from datetime import datetime
import json
import uuid
from typing import Any, Dict, Optional

from common.service.service_template import ServiceTemplate
from common.models.api.redis_models import Message, StreamMessage
from common.redis_client.publisher import Publisher
from microservices.retrieval_layer.processor import process_nlp_message
from microservices.retrieval_layer.config import (
    USER_OUTPUT_STREAM,
    FAILURE_OUTPUT_STREAM,
)
from logging import getLogger
from pydantic import ValidationError

logger = getLogger(__name__)


class RetrievalService(ServiceTemplate):
    def __init__(self):
        super().__init__()
        self.publisher = Publisher()

    # -------------------------------
    # 1. Parse Redis message
    # -------------------------------
    def _parse_message(self, raw_msg: Dict[str, Any]) -> Optional[StreamMessage]:
        msg_data = raw_msg.get("data", {})

        try:
            if "header" in msg_data:
                reconstructed = {
                    "header": json.loads(msg_data["header"]),
                    "payload": json.loads(msg_data.get("payload", "{}")),
                    "stage_timestamps": json.loads(msg_data.get("stage_timestamps", "[]")),
                }
            else:
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

        message_dict = {
            "article": {
                "url": payload.article_url,
                "title": payload.title,
                "text": payload.parsed_text,
                "html": payload.raw_html,
                "publishedAt": payload.publish_date,
                "outlet_name": payload.news_outlet,
            },
            "claims": [
                {
                    "original_sentence": c.get("original_sentence"),
                    "decontextualised_claim": c.get("decontextualised_claim"),
                    "decontextualised_embedding": c.get("decontextualised_embedding"),
                    "centrality_score": c.get("centrality_score"),
                    "entities": c.get("entities", []),
                }
                for c in payload.claims_in_article
            ],
        }

        result = process_nlp_message(message_dict)

        # publish success
        self.publisher.publish(
            USER_OUTPUT_STREAM,
            {
                "job_uid": message.data.header.uid,
                "status": "completed",
                "retrieval_result": result,
            },
        )

        return message

    # -------------------------------
    # 3. Failure handling
    # -------------------------------
    def _handle_failure(self, raw_msg: Dict[str, Any], error: Exception):
        logger.error("Routing message to failure stream")

        self.publisher.publish(
            FAILURE_OUTPUT_STREAM,
            {
                "error": str(error),
                "raw_message": raw_msg,
                "failed_at": datetime.utcnow().isoformat(),
            },
        )
