import unittest

from common.models.api.dtos.job import JobStage, JobStatus, JobType
from common.models.api.redis_models import Message, MessagePayload, add_timestamp_to_message


class TestJobEnumContract(unittest.TestCase):
    def test_job_status_values_are_frozen(self):
        self.assertEqual(
            [item.value for item in JobStatus],
            ["pending", "complete", "failed"],
        )

    def test_job_type_values_are_frozen(self):
        self.assertEqual(
            [item.value for item in JobType],
            ["background", "user"],
        )

    def test_job_stage_values_are_frozen(self):
        self.assertEqual(
            [item.value for item in JobStage],
            [
                "ingested",
                "prioritised",
                "starting fetch HTML",
                "ending fetch HTML",
                "starting parsing HTML",
                "ending parsing HTML",
                "started NLP",
                "completed NLP",
                "in",
                "out",
            ],
        )


class TestRedisMessageContract(unittest.TestCase):
    def test_ingestor_style_message_is_valid(self):
        raw_message = {
            "header": {
                "id": None,
                "uid": "job-uid-1",
                "type": "background",
                "status": "pending",
                "created_at": "2026-03-13T10:00:00",
            },
            "payload": {
                "article_url": "https://example.com/article-1",
                "news_outlet": "Example News",
                "title": "Example title",
                "summary": "Example summary",
            },
            "stage_timestamps": [
                {
                    "job_uid": "job-uid-1",
                    "stage_name": "ingested",
                    "wall_time": "2026-03-13T10:00:01",
                    "offset_s": 0.1,
                }
            ],
        }

        parsed = Message.model_validate(raw_message)
        self.assertEqual(parsed.header.type, "background")
        self.assertEqual(parsed.header.status, "pending")
        self.assertEqual(parsed.payload.article_url, "https://example.com/article-1")
        self.assertEqual(parsed.stage_timestamps[0].stage_name, "ingested")

    def test_message_round_trip_preserves_transport_shape(self):
        message = Message.model_validate(
            {
                "header": {
                    "id": 12,
                    "uid": "job-uid-2",
                    "type": "user",
                    "status": "pending",
                    "created_at": "2026-03-13T11:00:00",
                },
                "payload": {
                    "article_url": "https://example.com/article-2",
                    "news_outlet": "Example Outlet",
                    "title": "Title 2",
                    "raw_html": "<html></html>",
                    "parsed_text": "Hello world",
                },
                "stage_timestamps": [],
            }
        )

        dumped = message.model_dump()
        self.assertIn("header", dumped)
        self.assertIn("payload", dumped)
        self.assertIn("stage_timestamps", dumped)
        self.assertEqual(dumped["header"]["uid"], "job-uid-2")
        self.assertEqual(dumped["payload"]["article_url"], "https://example.com/article-2")

        reparsed = Message.model_validate(dumped)
        self.assertEqual(reparsed.header.uid, "job-uid-2")
        self.assertEqual(reparsed.payload.parsed_text, "Hello world")

    def test_add_timestamp_uses_stage_contract(self):
        message = Message.model_validate(
            {
                "header": {
                    "id": None,
                    "uid": "job-uid-3",
                    "type": "background",
                    "status": "pending",
                    "created_at": "2026-03-13T12:00:00",
                },
                "payload": MessagePayload(article_url="https://example.com/article-3").model_dump(),
                "stage_timestamps": [],
            }
        )

        updated = add_timestamp_to_message(message, JobStage.INGESTED)
        updated = add_timestamp_to_message(updated, JobStage.NLP_START)

        self.assertEqual(len(updated.stage_timestamps), 2)
        self.assertEqual(updated.stage_timestamps[0].stage_name, "ingested")
        self.assertEqual(updated.stage_timestamps[1].stage_name, "started NLP")


if __name__ == "__main__":
    unittest.main()
