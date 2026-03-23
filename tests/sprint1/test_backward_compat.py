import unittest

from common.models.api.redis_models import (
    BiasProfile,
    Claim,
    Entity,
    Message,
    MessageHeader,
    MessagePayload,
    NLPResult,
    StreamMessage,
)


class TestMessageBackwardCompatibility(unittest.TestCase):
    def test_message_with_legacy_extra_payload_fields_still_parses(self):
        raw_message = {
            "header": {
                "id": 1,
                "uid": "legacy-uid",
                "type": "background",
                "status": "pending",
                "created_at": "2026-03-13T13:00:00",
            },
            "payload": {
                "article_url": "https://example.com/legacy",
                "news_outlet": "Legacy News",
                "legacy_priority": "high",
                "legacy_source_id": "old-123",
            },
            "stage_timestamps": [
                {
                    "job_uid": "legacy-uid",
                    "stage_name": "ingested",
                    "wall_time": "2026-03-13T13:00:01",
                    "offset_s": 0.5,
                }
            ],
        }

        parsed = Message.model_validate(raw_message)

        self.assertEqual(parsed.payload.article_url, "https://example.com/legacy")
        self.assertFalse(hasattr(parsed.payload, "legacy_priority"))
        self.assertFalse(hasattr(parsed.payload, "legacy_source_id"))

    def test_nlp_payload_round_trip_with_claims_and_entities(self):
        raw_message = {
            "header": {
                "id": 2,
                "uid": "nlp-uid",
                "type": "user",
                "status": "pending",
                "created_at": "2026-03-13T13:10:00",
            },
            "payload": {
                "article_url": "https://example.com/nlp",
                "claims_in_article": [
                    {
                        "confidence": 0.83,
                        "source_sentence_indices": [0],
                        "decontextualised_claim_text": "Government increased taxes.",
                        "decontextualised_claim_embedding": [0.1, 0.2, 0.3],
                        "NER_entities": [
                            {
                                "entity_text": "Government",
                                "type_of_entity": "ORG",
                                "start_char": 0,
                                "end_char": 10,
                            }
                        ],
                    }
                ],
                "entities_in_article": [
                    {
                        "entity_text": "Government",
                        "type_of_entity": "ORG",
                        "start_char": 0,
                        "end_char": 10,
                    }
                ],
                "bias_profile": {
                    "political_bias": "Center",
                    "confidence": 0.7,
                    "scores": {"Left": 0.1, "Center": 0.8, "Right": 0.1},
                    "emotional_tone": "Neutral",
                },
            },
            "stage_timestamps": [],
        }

        parsed = Message.model_validate(raw_message)
        dumped = parsed.model_dump()

        self.assertEqual(dumped["payload"]["claims_in_article"][0]["decontextualised_claim_text"], "Government increased taxes.")
        self.assertEqual(dumped["payload"]["entities_in_article"][0]["entity_text"], "Government")
        self.assertEqual(dumped["payload"]["bias_profile"]["political_bias"], "Center")

    def test_set_nlp_result_does_not_overwrite_existing_payload_fields(self):
        original_claim = Claim(
            confidence=0.5,
            source_sentence_indices=[0],
            decontextualised_claim_text="Existing claim",
        )
        original_entity = Entity(
            entity_text="Existing",
            type_of_entity="ORG",
            start_char=0,
            end_char=8,
        )
        original_bias = BiasProfile(
            political_bias="Left",
            confidence=0.6,
            scores={"Left": 0.6, "Center": 0.3, "Right": 0.1},
            emotional_tone="Neutral",
        )

        message = Message(
            header=MessageHeader(
                id=3,
                uid="uid-existing",
                type="user",
                status="pending",
                created_at="2026-03-13T13:20:00",
            ),
            payload=MessagePayload(
                article_url="https://example.com/existing",
                claims_in_article=[original_claim],
                entities_in_article=[original_entity],
                bias_profile=original_bias,
            ),
            stage_timestamps=[],
        )

        stream_message = StreamMessage(
            stream="user:to.be.nlp",
            redis_id="1-0",
            priority=1,
            data=message,
        )

        new_result = NLPResult(
            claims_in_article=[
                Claim(
                    confidence=0.9,
                    source_sentence_indices=[1],
                    decontextualised_claim_text="New claim",
                )
            ],
            entities_in_article=[
                Entity(
                    entity_text="New",
                    type_of_entity="ORG",
                    start_char=0,
                    end_char=3,
                )
            ],
            bias_profile=BiasProfile(
                political_bias="Right",
                confidence=0.9,
                scores={"Left": 0.1, "Center": 0.1, "Right": 0.8},
                emotional_tone="Positive",
            ),
        )

        stream_message.set_nlp_result(new_result)

        self.assertEqual(stream_message.data.payload.claims_in_article[0].decontextualised_claim_text, "Existing claim")
        self.assertEqual(stream_message.data.payload.entities_in_article[0].entity_text, "Existing")
        self.assertEqual(stream_message.data.payload.bias_profile.political_bias, "Left")


if __name__ == "__main__":
    unittest.main()
