import unittest
import importlib
import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

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


class TestRetrievalProcessorSmoke(unittest.TestCase):
    @staticmethod
    def _load_processor_with_stubs(fake_db, article_obj, claim_side_effect):
        module_name = "microservices.retrieval_layer.processor"
        sys.modules.pop(module_name, None)

        crud_stub = types.ModuleType("microservices.retrieval_layer.storage.crud")
        session_stub = types.ModuleType("microservices.retrieval_layer.db.session")

        crud_stub.get_or_create_article = MagicMock(return_value=article_obj)
        crud_stub.create_claim_and_link_entities = MagicMock(side_effect=claim_side_effect)
        session_stub.get_db_session = MagicMock(return_value=fake_db)

        with patch.dict(
            sys.modules,
            {
                "microservices.retrieval_layer.storage.crud": crud_stub,
                "microservices.retrieval_layer.db.session": session_stub,
            },
        ):
            processor = importlib.import_module(module_name)

        return processor, crud_stub, session_stub

    def test_process_nlp_message_commits_and_returns_ids(self):
        fake_db = MagicMock()
        fake_article = SimpleNamespace(id=101)

        claim_ids = [1001, 1002]
        created_claims = [SimpleNamespace(id=i) for i in claim_ids]

        processor, crud_stub, session_stub = self._load_processor_with_stubs(
            fake_db=fake_db,
            article_obj=fake_article,
            claim_side_effect=created_claims,
        )

        message = {
            "article": {"url": "https://example.com", "title": "T"},
            "claims": [
                {"decontextualised_claim": "A"},
                {"decontextualised_claim": "B"},
            ],
        }

        result = processor.process_nlp_message(message)

        self.assertEqual(result["created_article_id"], 101)
        self.assertEqual(result["created_claim_ids"], claim_ids)
        session_stub.get_db_session.assert_called_once()
        crud_stub.get_or_create_article.assert_called_once()
        self.assertEqual(crud_stub.create_claim_and_link_entities.call_count, 2)
        fake_db.commit.assert_called_once()
        fake_db.rollback.assert_not_called()
        fake_db.close.assert_called_once()

    def test_process_nlp_message_rolls_back_on_error(self):
        fake_db = MagicMock()
        fake_article = SimpleNamespace(id=101)

        processor, crud_stub, session_stub = self._load_processor_with_stubs(
            fake_db=fake_db,
            article_obj=fake_article,
            claim_side_effect=RuntimeError("db error"),
        )

        message = {
            "article": {"url": "https://example.com", "title": "T"},
            "claims": [{"decontextualised_claim": "A"}],
        }

        with self.assertRaises(RuntimeError):
            processor.process_nlp_message(message)

        session_stub.get_db_session.assert_called_once()
        crud_stub.get_or_create_article.assert_called_once()
        crud_stub.create_claim_and_link_entities.assert_called_once()
        fake_db.commit.assert_not_called()
        fake_db.rollback.assert_called_once()
        fake_db.close.assert_called_once()


class TestRetrievalNLISmoke(unittest.TestCase):
    def test_nli_pipeline_is_cached(self):
        from microservices.retrieval_layer.retrieval import nli

        nli._nli = None

        calls = []

        class FakePipeline:
            def __call__(self, _payload, truncation=True):
                return {"label": "ENTAILMENT", "score": 0.91}

        def fake_pipeline(*args, **kwargs):
            calls.append((args, kwargs))
            return FakePipeline()

        with patch.object(nli, "pipeline", side_effect=fake_pipeline):
            label1, conf1 = nli.classify_claim_relation("u1", "c1")
            label2, conf2 = nli.classify_claim_relation("u2", "c2")

        self.assertEqual(label1, "support")
        self.assertEqual(label2, "support")
        self.assertGreater(conf1, 0.0)
        self.assertGreater(conf2, 0.0)
        self.assertEqual(len(calls), 1, "Pipeline should be initialized only once")


class TestStreamMessageSmoke(unittest.TestCase):
    def test_set_nlp_result_populates_payload(self):
        message = Message(
            header=MessageHeader(
                uid="uid-1",
                type="user",
                status="pending",
                created_at="2026-03-13T00:00:00+00:00",
            ),
            payload=MessagePayload(article_url="https://example.com", parsed_text="hello"),
            stage_timestamps=[],
        )

        stream_message = StreamMessage(
            stream="user:to.be.nlp",
            redis_id="0-1",
            priority=1,
            data=message,
        )

        nlp_result = NLPResult(
            claims_in_article=[
                Claim(
                    confidence=0.8,
                    source_sentence_indices=[0],
                    decontextualised_claim_text="Test claim",
                    decontextualised_claim_embedding=[0.1, 0.2, 0.3],
                    NER_entities=[
                        Entity(
                            entity_text="Government",
                            type_of_entity="ORG",
                            start_char=0,
                            end_char=10,
                        )
                    ],
                )
            ],
            entities_in_article=[
                Entity(
                    entity_text="Government",
                    type_of_entity="ORG",
                    start_char=0,
                    end_char=10,
                )
            ],
            bias_profile=BiasProfile(
                political_bias="Center",
                confidence=0.7,
                scores={"Left": 0.2, "Center": 0.7, "Right": 0.1},
                emotional_tone="Neutral",
            ),
        )

        stream_message.set_nlp_result(nlp_result)

        self.assertEqual(len(stream_message.data.payload.claims_in_article), 1)
        self.assertEqual(len(stream_message.data.payload.entities_in_article), 1)
        self.assertIsNotNone(stream_message.data.payload.bias_profile)


if __name__ == "__main__":
    unittest.main()
