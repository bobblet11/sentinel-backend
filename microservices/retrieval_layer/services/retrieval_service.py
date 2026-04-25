from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import torch
from requests import Session

from common.io.json_updater import JsonHandler
from common.models.api.dtos.job import JobStage, JobStatus, JobType
from common.models.api.redis_models import (
    Claim,
    Message,
    MessagePayload,
    RetrievalResult,
    StreamMessage,
)
from common.models.api.validation_helpers import (
    get_pretty_print_stream_message,
    validate_after_retrieval,
)
from common.redis_client.duplicate_filter import RedisDuplicateFilter
from common.redis_client.hash_store import RedisHashStore
from common.service.service_template import ServiceTemplate
from microservices.retrieval_layer.config import (
    HASH_STORE_NAMESPACE,
    IS_BENCHMARK,
    UID_STORE_NAMESPACE,
)
from microservices.retrieval_layer.db.session import get_db_transaction
from microservices.retrieval_layer.retrieval.embedding_retriever import (
    retrieve_by_embedding,
)
from microservices.retrieval_layer.retrieval.entity_filter import (
    find_evidence_by_entity_match,
)
from microservices.retrieval_layer.retrieval.keyword_filter import (
    find_evidence_by_keyword_match,
)
from microservices.retrieval_layer.retrieval.nli import classify_claim_relation
from microservices.retrieval_layer.storage.crud import (
    create_claim_and_link_entities,
    extend_evidence_claims_into_articles,
    finalise_and_complete_job,
    get_or_create_all_entities,
    get_or_create_article,
    upsert_article_topic,
)
from microservices.retrieval_layer.storage.dtos import (
    CreateOrModifyArticle,
    CreateOrModifyClaim,
    CreateOrModifyOutlet,
    CreateOrModifySentiment,
    UpdateJob,
    UpsertArticleTopic,
)

MAX_CANDIDATES_BEFORE_SIMILARITY = 100
MAX_CANDIDATES_BEFORE_NLI = 10
MIN_SIMILARITY = 0.25
EMBEDDING_DIM = 768


class RetrievalService(ServiceTemplate):
    def __init__(self, config):
        super().__init__(config)
        self.hash_store = RedisHashStore(hash_namespace=HASH_STORE_NAMESPACE)
        self.uid_store = RedisDuplicateFilter(key_name=UID_STORE_NAMESPACE, ttl_s=0)
        if torch.cuda.is_available():
            self.logger.info("GPU DETECTED")
        else:
            self.logger.info("GPU NOT DETECTED")

        self.stats_json_handler = JsonHandler(filename="stats.json")

    def _log_stats(
        self,
        news_outlet: str,
        input_claims_evaluated: int,
        evidence_matches: int,
        verdicts: List[str],
        confidences: List[float | int],
        related_articles: int,
        error_type: Optional[str] = None,
    ) -> None:

        data = self.stats_json_handler.read_json()
        day_key = datetime.now().date().isoformat()

        entry = data.setdefault(
            day_key,
            {
                "user_jobs_processed": 0,
                "input_claims_evaluated": 0,
                "evidence_matches": 0,
                "verdicts": {
                    "true": 0,
                    "mostly-true": 0,
                    "mixed": 0,
                    "mostly-false": 0,
                    "false": 0,
                    "unverified": 0,
                },
                "confidence_scores": {"sum": 0, "count": 0, "min": None, "max": None},
                "relations": {"support": 0, "contradict": 0, "irrelevant": 0},
                "related_articles_total": 0,
                "errors": {},
                "outlet_stats": {},
            },
        )

        # Global updates
        entry["user_jobs_processed"] += 1
        entry["input_claims_evaluated"] += input_claims_evaluated
        entry["evidence_matches"] += evidence_matches

        for verdict in verdicts:
            if verdict in entry["verdicts"]:
                entry["verdicts"][verdict] += 1
            else:
                entry["verdicts"][verdict] = 1

        entry["confidence_scores"]["sum"] += sum(confidences)
        entry["confidence_scores"]["count"] += 1
        max_confidence = max(confidences)
        min_confidence = min(confidences)
        entry["confidence_scores"]["min"] = (
            min_confidence
            if entry["confidence_scores"]["min"] is None
            else min(entry["confidence_scores"]["min"], min_confidence)
        )
        entry["confidence_scores"]["max"] = (
            max_confidence
            if entry["confidence_scores"]["max"] is None
            else max(entry["confidence_scores"]["max"], max_confidence)
        )

        entry["related_articles_total"] += related_articles

        if error_type:
            entry["errors"][error_type] = entry["errors"].get(error_type, 0) + 1

        # Outlet‑level stats
        outlet_entry = entry["outlet_stats"].setdefault(
            news_outlet,
            {
                "count": 0,
                "input_claims_evaluated": 0,
                "evidence_matches": 0,
                "verdicts": {
                    "true": 0,
                    "mostly-true": 0,
                    "mixed": 0,
                    "mostly-false": 0,
                    "false": 0,
                    "unverified": 0,
                },
                "errors": {},
            },
        )
        outlet_entry["count"] += 1
        outlet_entry["input_claims_evaluated"] += input_claims_evaluated
        outlet_entry["evidence_matches"] += evidence_matches

        for verdict in verdicts:
            if verdict in outlet_entry["verdicts"]:
                outlet_entry["verdicts"][verdict] += 1
            else:
                outlet_entry["verdicts"][verdict] = 1

        if error_type:
            outlet_entry["errors"][error_type] = (
                outlet_entry["errors"].get(error_type, 0) + 1
            )

        # Prune to last 30 days
        MAX_DAYS = 30
        dates = sorted(data.keys())
        if len(dates) > MAX_DAYS:
            for old_date in dates[:-MAX_DAYS]:
                del data[old_date]

        self.stats_json_handler.write_json(data)

    @staticmethod
    def _normalize_embedding(embedding: List[float] | None) -> List[float] | None:
        """Coerce embeddings to the pgvector dimension (pad/truncate) while preserving values."""
        if embedding is None:
            return None
        if not isinstance(embedding, list):
            return None

        try:
            normalized = [float(v) for v in embedding]
        except (TypeError, ValueError):
            return None

        if len(normalized) == EMBEDDING_DIM:
            return normalized
        if len(normalized) > EMBEDDING_DIM:
            return normalized[:EMBEDDING_DIM]

        # Zero-pad shorter embeddings (e.g., 384-dim MiniLM) to match Vector(768).
        return normalized + [0.0] * (EMBEDDING_DIM - len(normalized))

    def _calculate_verdict_and_confidence(
        self, matches: List[Dict[str, Any]]
    ) -> tuple[str, int]:
        """
        Calculate verdict and confidence for a claim based on its retrieval matches.

        Verdict: "true" | "mostly-true" | "mixed" | "mostly-false" | "false" | "unverified"
        Confidence: 0-100 integer
        """

        if not matches:
            return "unverified", 0

        support_count = sum(1 for m in matches if m["relation"] == "support")
        contradict_count = sum(1 for m in matches if m["relation"] == "contradict")
        irrelevant_count = sum(1 for m in matches if m["relation"] == "irrelevant")
        total = len(matches)

        # High-similarity "irrelevant" matches: NLI tends to over-predict neutral.
        # Treat them as soft support so they don't silently suppress a verdict.
        HIGH_SIM_THRESHOLD = 0.6
        soft_support_count = sum(
            1
            for m in matches
            if m["relation"] == "irrelevant" and m["similarity"] >= HIGH_SIM_THRESHOLD
        )
        effective_support = support_count + soft_support_count
        effective_irrelevant = irrelevant_count - soft_support_count

        # Verdict based on effective support/contradict counts
        if effective_irrelevant == total or (
            effective_support == 0 and contradict_count == 0
        ):
            verdict = "unverified"
        elif contradict_count == 0:
            verdict = "true" if support_count == total else "mostly-true"
        elif effective_support == 0:
            verdict = "false" if contradict_count == total else "mostly-false"
        else:
            support_ratio = effective_support / (effective_support + contradict_count)
            if support_ratio > 0.66:
                verdict = "mostly-true"
            elif support_ratio < 0.33:
                verdict = "mostly-false"
            else:
                verdict = "mixed"

        # Confidence: composite of match quality, similarity, and NLI confidence
        high_quality_matches = [
            m
            for m in matches
            if m["similarity"] > 0.5 and m["relation"] != "irrelevant"
        ]
        high_confidence_matches = [
            m for m in high_quality_matches if m["confidence"] >= 0.9
        ]

        if not high_quality_matches:
            confidence = 20
        else:
            match_count_score = min(len(high_quality_matches) * 20, 60)
            avg_similarity = sum(m["similarity"] for m in high_quality_matches) / len(
                high_quality_matches
            )
            similarity_score = int(avg_similarity * 30)
            high_conf_bonus = min(len(high_confidence_matches) * 10, 10)
            confidence = min(
                match_count_score + similarity_score + high_conf_bonus, 100
            )

        return verdict, confidence

    def _save_data_into_postgres(self, db: Session, message: StreamMessage):

        claims: List[Claim] = message.all_claims or []

        self.logger.debug("Saving article uid=%s claims=%d", message.uid, len(claims))
        bias_profile = message.bias_profile

        # Guard against None bias_profile when NLP bias detection fails
        if bias_profile is None:
            self.logger.warning(
                "bias_profile is None for uid=%s, using defaults", message.uid
            )
            sentiment_dto = CreateOrModifySentiment(
                bias_category="center",
                # bias_score=0.0,
                bias_analysis_confidence=0.0,
                sentiment_category="neutral",
                sentiment_analysis_confidence=0.0,
            )
        else:
            sentiment_dto = CreateOrModifySentiment(
                bias_profile.bias_category,
                # bias_profile.bias_score,
                bias_profile.bias_analysis_confidence,
                bias_profile.sentiment_category,
                bias_profile.sentiment_analysis_confidence,
            )

        article_dto = CreateOrModifyArticle(
            message.link,
            message.title,
            message.text,
            message.html,
            message.publish_date,
            message.data.payload.author,
        )
        outlet_dto = CreateOrModifyOutlet(message.news_outlet_name)

        article_entry = get_or_create_article(
            db, article_dto, sentiment_dto, outlet_dto
        )

        all_entities_added = []
        all_claims_added = []

        for claim in claims:
            raw_embedding = claim.decontextualised_claim_embedding
            normalized_embedding = self._normalize_embedding(raw_embedding)
            if raw_embedding is not None and normalized_embedding is None:
                self.logger.warning(
                    "Skipping invalid embedding values for claim text=%r",
                    (claim.decontextualised_claim_text or "")[:80],
                )

            claim_dto = CreateOrModifyClaim(
                claim.decontextualised_claim_text,
                claim.decontextualised_claim_text,
                normalized_embedding,
                claim.confidence,
                NER_entities=claim.NER_entities,
            )
            new_claim_entry = create_claim_and_link_entities(
                db, claim_dto, article_entry
            )
            entities_added = get_or_create_all_entities(db, claim_dto.NER_entities)

            all_entities_added.extend(entities_added)
            all_claims_added.append(new_claim_entry)

        self.logger.debug(
            "Saved article id=%s claims=%d entities=%d",
            article_entry.id,
            len(all_claims_added),
            len(all_entities_added),
        )

        topic_label = message.data.payload.topic_label
        if topic_label:
            try:
                with db.begin_nested():
                    upsert_article_topic(
                        db,
                        UpsertArticleTopic(
                            article_id=article_entry.id,
                            topic_label=topic_label,
                            topic_confidence=message.data.payload.topic_confidence
                            or 0.0,
                        ),
                    )
            except Exception as e:
                self.logger.warning("topic upsert failed uid=%s: %s", message.uid, e)

        return {
            "article_entry_id": article_entry.id,
            "all_entity_ids_added": [x.id for x in all_entities_added],
            "all_claim_ids_added": [x.id for x in all_claims_added],
        }

    def _retrieve_evidence_for_claim(
        self,
        db: Session,
        claim: Claim,
        original_article_id: int,
        publish_date: str | None = None,
    ) -> List[int | str]:
        input_claim_text = claim.decontextualised_claim_text or ""
        claim_candidates = set()

        def filter_step() -> List[int | str]:
            # Parse article publish date for ±30 day window
            published_after = None
            published_before = None

            if publish_date:
                try:
                    article_date = datetime.fromisoformat(
                        publish_date.replace("Z", "+00:00")
                    )
                    published_after = article_date - timedelta(days=30)
                    published_before = article_date + timedelta(days=30)
                except Exception:
                    pass

            keyword_candidates = find_evidence_by_keyword_match(
                db,
                input_claim_text,
                limit=20,
                exclude_article_id=original_article_id,
                published_after=published_after,
                published_before=published_before,
            )
            claim_candidates.update(keyword_candidates)
            entities_in_claim = [entity.entity_text for entity in claim.NER_entities]
            entity_candidates = find_evidence_by_entity_match(
                db,
                entities_in_claim,
                50,
                exclude_article_id=original_article_id,
                published_after=published_after,
                published_before=published_before,
            )
            claim_candidates.update(entity_candidates)

            capped_filter_step_candidate_list = list(claim_candidates)[
                :MAX_CANDIDATES_BEFORE_SIMILARITY
            ]
            # list of db Claim objects
            capped_filter_step_candidate_ids = [
                filtered_claim.id
                for filtered_claim in capped_filter_step_candidate_list
            ]
            return capped_filter_step_candidate_ids

        def similarity_step(
            capped_filter_step_candidate_ids,
        ) -> List[Tuple[Dict[str, str | int], float]]:
            claim_text_embedding = self._normalize_embedding(
                claim.decontextualised_claim_embedding
            )
            if claim_text_embedding is None:
                self.logger.warning(
                    "Skipping similarity step due to invalid claim embedding for claim=%r",
                    (input_claim_text or "")[:80],
                )
                return []

            best_ranked_similarity_evidence = retrieve_by_embedding(
                db,
                claim_text_embedding,
                capped_filter_step_candidate_ids,
                exclude_article_id=original_article_id,
            )

            best_ranked_similarity_evidence = [
                (claim_dict, similarity)
                for claim_dict, similarity in best_ranked_similarity_evidence
                if similarity >= MIN_SIMILARITY
            ]

            if not best_ranked_similarity_evidence:
                return []

            capped_similarity_step_candidate_list = best_ranked_similarity_evidence[
                :MAX_CANDIDATES_BEFORE_NLI
            ]
            return capped_similarity_step_candidate_list

        def classification_step(
            capped_similarity_step_candidate_list,
        ) -> List[Tuple[Dict, float, str, float]]:
            classified_evidence = []

            for (
                evidence_claim,
                similarity_score,
            ) in capped_similarity_step_candidate_list:
                claim_id = evidence_claim.get("id", "unknown")
                try:
                    label, confidence = classify_claim_relation(
                        input_claim_text, evidence_claim.get("decontextualised_claim")
                    )
                    self.logger.debug(
                        f"NLI claim {claim_id}: {label} (confidence: {confidence:.2f})"
                    )
                except (RuntimeError, ValueError, KeyError, TypeError) as e:
                    self.logger.error(
                        f"NLI failed for claim {claim_id}: {type(e).__name__}: {e}"
                    )
                    label, confidence = "irrelevant", 0.0
                except Exception as e:
                    self.logger.error(
                        f"Unexpected NLI error for claim {claim_id}: {type(e).__name__}: {e}"
                    )
                    label, confidence = "irrelevant", 0.0

                classified_evidence.append(
                    (evidence_claim, similarity_score, label, confidence)
                )
            return classified_evidence

        evidence_matches = [
            {
                "claim_id": int(claim_dict.get("id")),
                "claim_text": claim_dict.get("decontextualised_claim"),
                "source_article_id": claim_dict.get("article_id"),
                "source_url": claim_dict.get("source_url"),
                "source_excerpt": claim_dict.get("source_excerpt"),
                "similarity": float(similarity),
                "relation": classification_label,
                "confidence": confidence,
                "query_claim": input_claim_text,
            }
            for claim_dict, similarity, classification_label, confidence in classification_step(
                similarity_step(filter_step())
            )
            if claim_dict.get("article_id") != original_article_id
        ]

        total_verdict, total_confidence_score = self._calculate_verdict_and_confidence(
            evidence_matches
        )

        claim_evidence_results = {
            "query_claim": input_claim_text,
            "verdict": total_verdict,
            "confidence": total_confidence_score,
            "matches": evidence_matches,
            "match_count": len(evidence_matches),
        }

        return claim_evidence_results

    def _retrieve_evidence(
        self, db: Session, message: StreamMessage, original_article_id: int
    ):
        # Evaluate each input claim to get evidence matches, verdict, and confidence.
        # Keep one output row per input claim (do not merge by claim text).
        claim_results: List[Dict[str, Any]] = []
        evidence_claim_ids = []

        for input_claim in message.all_claims or []:
            input_claim_evaluation = self._retrieve_evidence_for_claim(
                db=db,
                claim=input_claim,
                original_article_id=original_article_id,
                publish_date=message.publish_date,
            )
            claim_results.append(input_claim_evaluation)
            evidence_claim_ids.extend(
                [
                    evidence_claim.get("claim_id")
                    for evidence_claim in input_claim_evaluation.get("matches", [])
                ]
            )

        related_articles = extend_evidence_claims_into_articles(
            db=db, claim_ids=evidence_claim_ids, current_article_id=original_article_id
        )

        self.logger.info(
            "Retrieval matches on job uid=%s claim_matches=%s",
            # message.data.header.uid,
            message.header.uid,
            len(evidence_claim_ids),
        )

        return claim_results, related_articles

    def _save_job_into_postgres(self, db: Session, message: StreamMessage):
        job_dto = UpdateJob(
            message.header.id,
            message.header.uid,
            JobStatus.COMPLETE,
            message.stage_timestamps,
        )
        job_entry = finalise_and_complete_job(db, job_dto)
        self.logger.debug(
            "Saved job id=%s uid=%s status=%s",
            job_entry.id,
            job_entry.uid,
            job_entry.status,
        )
        # return job_entry
        return {
            "job_id": job_entry.id,
            "job_uid": job_entry.uid,
            "status": job_entry.status,
            "type": job_entry.type,
        }

    def _process_and_publish_worker(self, message: StreamMessage) -> Tuple[str, str]:
        """Worker for concurrent mode. Processes, then publishes."""
        try:
            processed_message: StreamMessage = self._process_message(message)

            if IS_BENCHMARK:
                payload = processed_message.data.model_dump(mode="json")
                new_redis_id = self.success_publish_router.publish_one(payload)
                self.logger.debug(
                    f" [BENCHMARK] Successfully published Msg {message.redis_id} -> {new_redis_id} to stream"
                )
                return message.redis_id, new_redis_id

            payload = processed_message.retrieval_results or {}
            new_id = "END OF PIPELINE"
            if message.type == JobType.USER:
                self.hash_store.set(message.uid, payload)
                new_id = message.uid
                matches = payload.get("matches") or []
                related_articles = payload.get("related_articles") or []
                self.logger.info(
                    "Stored result uid=%s matches=%d related_articles=%d",
                    message.uid,
                    len(matches),
                    len(related_articles),
                )

            minimum_message: Message = Message(
                header=message.data.header,
                payload=MessagePayload(article_url=message.link),
                stage_timestamps=message.stage_timestamps,
            )

            self.uid_store.add_one(str(message.uid))
            self.success_publish_router.publish_one(
                minimum_message.model_dump(mode="json")
            )

            if self.is_cut_and_paste_mode:
                self.message_consumer.acknowledge_and_delete(
                    message.stream, message.redis_id
                )
            else:
                self.message_consumer.acknowledge(message.stream, message.redis_id)

            return message.redis_id, new_id  # id in hashset

        except Exception as e:
            # Catch any exception, including ProcessingError, and route to failure.
            self._handle_failure(message, e)
            # Raise it again so as_completed knows the future failed
            raise

    def _process_batch_sequentially(self, raw_messages: List[Dict[str, Any]]) -> None:

        stream_messages: List[StreamMessage] = [
            msg for m in raw_messages if (msg := self._parse_message(m))
        ]
        ack_count = 0
        failure_count = 0

        for message in stream_messages:
            try:
                processed_message = self._process_message(message)

                if IS_BENCHMARK:
                    payload = processed_message.data.model_dump(mode="json")
                    new_redis_id = self.success_publish_router.publish_one(payload)
                    self.logger.debug(
                        f" [BENCHMARK] Successfully published Msg {message.redis_id} -> {new_redis_id} to stream"
                    )
                    ack_count += 1

                payload = processed_message.retrieval_results or {}
                new_id = "END OF PIPELINE"
                if message.type == JobType.USER:
                    self.hash_store.set(message.uid, payload)
                    new_id = message.uid
                    matches = payload.get("matches") or []
                    related_articles = payload.get("related_articles") or []
                    self.logger.info(
                        "Stored result uid=%s matches=%d related_articles=%d",
                        message.uid,
                        len(matches),
                        len(related_articles),
                    )

                minimum_message: Message = Message(
                    header=message.data.header,
                    payload=MessagePayload(article_url=message.link),
                    stage_timestamps=message.stage_timestamps,
                )

                self.uid_store.add_one(str(message.uid))
                self.success_publish_router.publish_one(
                    minimum_message.model_dump(mode="json")
                )

                if self.is_cut_and_paste_mode:
                    self.message_consumer.acknowledge_and_delete(
                        message.stream, message.redis_id
                    )
                else:
                    self.message_consumer.acknowledge(message.stream, message.redis_id)

                self.logger.debug(
                    f"Successfully published Msg {message.redis_id} -> {new_id} in hashset and stats in {self.output_streams[0]}"
                )
                ack_count += 1

            except Exception as e:
                self.logger.warning(
                    f"Failed to publish message {message.redis_id}. See previous error logs for details."
                )
                self._handle_failure(message, e)
                failure_count += 1

        if failure_count > 0:
            self.logger.warning(
                f"Sent {failure_count} failed messages to failure stream."
            )

    def _process_batch_concurrently(
        self, executor: ThreadPoolExecutor, raw_messages: List[Dict[str, Any]]
    ):
        stream_messages = [msg for m in raw_messages if (msg := self._parse_message(m))]

        future_to_message = {
            executor.submit(self._process_and_publish_worker, msg): msg
            for msg in stream_messages
        }

        for future in as_completed(future_to_message):
            original_message = future_to_message[future]

            try:
                old_redis_id, new_redis_id = future.result()
                self.logger.debug(
                    f"Successfully published Msg {old_redis_id} -> {new_redis_id} in hashset and stats in {self.output_streams[0]}"
                )
            except Exception:
                self.logger.warning(
                    f"A worker for message {original_message.redis_id} failed. See previous error logs for details."
                )

    def _process_message(self, message: StreamMessage) -> StreamMessage:
        # one db session to make sure the entire thing is 1 transaction
        # just raise an exception and it will roll back everything
        with get_db_transaction() as db:
            message.add_timestamp(JobStage.SAVE_DATA_IN)
            save_data_result = self._save_data_into_postgres(db, message)
            message.add_timestamp(JobStage.SAVE_DATA_OUT)

            if message.type == JobType.BACKGROUND:
                self.logger.info("Background job complete uid=%s", message.header.uid)
                return message

            original_article_id = save_data_result.get("article_entry_id") or 0
            message.add_timestamp(JobStage.RETRIEVE_EVIDENCE_IN)
            claim_evidence_matches, related_articles = self._retrieve_evidence(
                db, message, original_article_id
            )
            message.add_timestamp(JobStage.RETRIEVE_EVIDENCE_OUT)

            message.add_timestamp(JobStage.UPDATE_JOB_IN)
            save_job_result = self._save_job_into_postgres(db, message)
            message.add_timestamp(JobStage.UPDATE_JOB_OUT)

            retrieval_result = RetrievalResult(
                save_data_result,
                save_job_result,
                claim_evidence_matches,
                related_articles,
            )

            # claim_evidence_results = {
            #     "query_claim": input_claim_text,

            #     "verdict": total_verdict,
            #     "confidence": total_confidence_score,

            #     "matches": evidence_matches,
            #     "match_count": len(evidence_matches),
            # }

            len_input_claims = len(message.all_claims or [])
            len_related_articles = len(related_articles or [])
            len_evidence_claims_found = sum(
                x.get("match_count", 0) for x in claim_evidence_matches
            )
            verdicts = [x.get("verdict", "unverified") for x in claim_evidence_matches]
            confidences = [x.get("confidence", 0) for x in claim_evidence_matches]

            self._log_stats(
                message.news_outlet_name,
                len_input_claims,
                len_evidence_claims_found,
                verdicts,
                confidences,
                len_related_articles,
            )
            message.set_retrieval_result(retrieval_result)
            self.logger.debug(get_pretty_print_stream_message(message))
            validate_after_retrieval(stream_message=message, message=None)

            return message
