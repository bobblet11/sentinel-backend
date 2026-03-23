from asyncio import as_completed
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Tuple

from requests import Session

from common.models.api.dtos.job import JobStage, JobStatus, JobType
from common.redis_client.hash_store import RedisHashStore
from common.service.service_template import ServiceTemplate
from common.models.api.redis_models import BiasProfile, Claim, Message, RetrievalResult, StreamMessage
from common.redis_client.publisher import RedisPublisher
from microservices.retrieval_layer.retrieval.common_words import STOP_WORDS
from microservices.retrieval_layer.retrieval.embedding_retriever import retrieve_by_embedding
from microservices.retrieval_layer.retrieval.entity_filter import find_evidence_by_entity_match
from microservices.retrieval_layer.retrieval.keyword_filter import find_evidence_by_keyword_match
from microservices.retrieval_layer.retrieval.nli import classify_claim_relation
from microservices.retrieval_layer.storage.dtos import CreateOrModifyArticle, CreateOrModifySentiment, CreateOrModifyOutlet, CreateOrModifyClaim, UpdateJob

from microservices.retrieval_layer.config import (
    HASH_STORE_NAMESPACE,
)

from microservices.retrieval_layer.db.session import get_db_session, get_db_transaction
from microservices.retrieval_layer.storage.crud import (
    extend_evidence_claims_into_articles,
    finalise_and_complete_job,
    get_or_create_all_entities,
    get_or_create_article,
    create_claim_and_link_entities,
)


MAX_CANDIDATES_BEFORE_SIMILARITY = 100
MAX_CANDIDATES_BEFORE_NLI = 10
MIN_SIMILARITY = 0.25
EMBEDDING_DIM = 768


class RetrievalService(ServiceTemplate):
    def __init__(self, config):
        super().__init__(config)
        self.hash_store = RedisHashStore(hash_namespace=HASH_STORE_NAMESPACE)

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
        
    def _calculate_verdict_and_confidence(self,matches: List[Dict[str, Any]]) -> tuple[str, int]:
        """
        Calculate verdict and confidence for a claim based on its retrieval matches.
        
        Verdict: "true" | "mostly-true" | "mixed" | "mostly-false" | "false" | "unverified"
        Confidence: 0-100 integer
        """
        
        if not matches:
            return "unverified", 0
        relevant = [m for m in matches if m["relation"] in ("support", "contradict")]
        if not relevant:
            return "unverified", 0
        
        # Calculate verdict ("true" | "mostly-true" | "mixed" | "mostly-false" | "false" | "unverified") based on:
        support_weight = sum(m["confidence"] for m in relevant if m["relation"] == "support")
        contradict_weight = sum(m["confidence"] for m in relevant if m["relation"] == "contradict")
        total_weight = support_weight + contradict_weight
        if total_weight == 0:
            self.logger.error("total weight is 0! Division by 0 error!")
            
        net_support = (support_weight - contradict_weight) / total_weight if total_weight > 0 else 0
        
        
        if net_support >= 0.5:
            verdict = "true"
        elif net_support >= 0.1:
            verdict = "mostly-true"
        elif net_support <= -0.5:
            verdict = "false"
        elif net_support <= 0.1:
            verdict = "mostly-false"
        else:
            verdict = "mixed"
        
        # Calculate confidence (0-100) based on:
        avg_quality = sum(m["similarity"] * m["confidence"] for m in relevant) / len(relevant)
        perfect_evidence = len(relevant) * 1.0  # Max quality = 1.0
        evidence_ratio = ( avg_quality * len(relevant) ) / perfect_evidence
        confidence = int(evidence_ratio * 100)
        return verdict, confidence

    def _save_data_into_postgres(self, db: Session, message: StreamMessage):
        
        claims: List[Claim] = message.all_claims 
        
        self.logger.debug(
                "=== SAVING JOB FOR ARTICLE ===\n"
                "\tuid=%s, title=%s\n"
                "\tNumber of claims: %d",
                message.uid,
                message.title,
                len(claims),
        )
        
        self.logger.debug("\t3 Claims from job")
        for i in range(min(3, len(claims))):
            self.logger.debug(
                "\tClaim %d: %s\n"
                "\t\tEmbedding sample (first 3 values): %s\n"
                "\t\tCentrality score: %.2f",
                i,
                claims[i].contextualised_claim_text,
                claims[i].decontextualised_claim_embedding[:3],
                claims[i].confidence,
            )
        
        bias_profile = message.bias_profile
        
        article_dto = CreateOrModifyArticle(message.link, message.title, message.text, message.html, message.publish_date)
        sentiment_dto = CreateOrModifySentiment(bias_profile.bias_category, bias_profile.bias_score, bias_profile.bias_analysis_confidence, bias_profile.sentiment_category, bias_profile.sentiment_analysis_confidence)
        outlet_dto = CreateOrModifyOutlet(message.news_outlet_name)
        
        article_entry = get_or_create_article(db, article_dto, sentiment_dto, outlet_dto)

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
                claim.contextualised_claim_text,
                claim.decontextualised_claim_text,
                normalized_embedding,
                claim.confidence,
                NER_entities=claim.NER_entities,
            )
            new_claim_entry = create_claim_and_link_entities(db, claim_dto, article_entry)
            entities_added = get_or_create_all_entities(db, claim_dto.NER_entities)
            
            all_entities_added.extend(entities_added)
            all_claims_added.append(new_claim_entry)
            
        self.logger.info(
            "DB write result article=%s claims=%s entities=%s (limited to 3 rows)",
            article_entry,
            all_entities_added[:3],
            all_claims_added[:3],
        )
        
        return {
            "article_entry_id": article_entry.id,
            "all_entity_ids_added" : [x.id for x in all_entities_added],
            "all_claim_ids_added" : [x.id for x in all_claims_added]
        }
        
    def _retrieve_evidence_for_claim(self, db: Session, claim: Claim, original_article_id: int) -> Dict[str, Any]:
        self.logger.debug("=== FINDING EVIDENCE ===\n")
        input_claim_text = claim.decontextualised_claim_text or claim.contextualised_claim_text or ""
        claim_candidates = set()
        
        def filter_step() -> List[int | str]:
            self.logger.debug("FILTERING")
            # for now, improve it with TD-IDF or whatever. this is just every word, not really keywords
            key_words_to_match = [
                x.strip(" .,;:'")
                for x in input_claim_text.split(" ")
                if x.strip(" .,;:'").lower() not in STOP_WORDS
            ]        
            # low limit because the matches are going to be low.
            self.logger.debug("FILTERING BY KEYWORD")
            keyword_candidates = find_evidence_by_keyword_match(
                db,
                key_words_to_match,
                20,
                exclude_article_id=original_article_id,
            )
            claim_candidates.update(keyword_candidates)
            entities_in_claim = [entity.entity_text for entity in claim.NER_entities]
            # higher limit because the matches are going to be higher.
            self.logger.debug("FILTERING BY ENTITY")
            entity_candidates = find_evidence_by_entity_match(
                db,
                entities_in_claim,
                50,
                exclude_article_id=original_article_id,
            )
            claim_candidates.update(entity_candidates)
        
            if not claim_candidates:
                return []
            
            capped_filter_step_candidate_list = list(claim_candidates)[:MAX_CANDIDATES_BEFORE_SIMILARITY]
            # list of db Claim objects
            capped_filter_step_candidate_ids = [filtered_claim.id for filtered_claim in capped_filter_step_candidate_list]
            return capped_filter_step_candidate_ids
        
        def similarity_step(capped_filter_step_candidate_ids) -> List[Tuple[Dict[str, str | int], float]]:
            self.logger.debug("SIMILARITY STEP")
            claim_text_embedding = self._normalize_embedding(claim.decontextualised_claim_embedding)
            if claim_text_embedding is None:
                self.logger.warning("Skipping similarity step due to invalid claim embedding for claim=%r", (input_claim_text or "")[:80])
                return []

            best_ranked_similarity_evidence = retrieve_by_embedding(
                db,
                claim_text_embedding,
                capped_filter_step_candidate_ids,
                exclude_article_id=original_article_id,
            )

            best_ranked_similarity_evidence = [
                (claim_dict, similarity)
                for claim_dict, similarity
                in best_ranked_similarity_evidence
                if similarity >= MIN_SIMILARITY
            ]
            
            if not best_ranked_similarity_evidence:
                return []
        
            capped_similarity_step_candidate_list = best_ranked_similarity_evidence[:MAX_CANDIDATES_BEFORE_NLI]
            return capped_similarity_step_candidate_list
        
        def classification_step(capped_similarity_step_candidate_list) -> List[Tuple[Dict, float, str, float]]:
            self.logger.debug("CLASSIFICATION STEP")
            classified_evidence = []
            
            for evidence_claim, similarity_score in capped_similarity_step_candidate_list:
                claim_id = evidence_claim.get("id", "unknown")
                try:
                    label, confidence = classify_claim_relation(
                        input_claim_text,
                        evidence_claim.get("decontextualised_claim")
                    )
                    self.logger.debug(f"NLI claim {claim_id}: {label} (confidence: {confidence:.2f})")
                except (RuntimeError, ValueError, KeyError, TypeError) as e:
                    self.logger.error(f"NLI failed for claim {claim_id}: {type(e).__name__}: {e}")
                    label, confidence = "irrelevant", 0.0
                except Exception as e:
                    self.logger.error(f"Unexpected NLI error for claim {claim_id}: {type(e).__name__}: {e}")
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
                "relation": classifcation_label,
                "confidence": confidence,
                "query_claim": input_claim_text,
            }
            for claim_dict, similarity, classifcation_label, confidence in classification_step(similarity_step(filter_step()))
            if claim_dict.get("article_id") != original_article_id
        ]
        
        total_verdict, total_confidence_score = self._calculate_verdict_and_confidence(evidence_matches)
            
        claim_evidence_results = { 
            "query_claim": input_claim_text,
            
            "verdict": total_verdict,
            "confidence": total_confidence_score,
            
            "matches": evidence_matches,
            "match_count": len(evidence_matches),
        }
        
        return claim_evidence_results
    
    def _retrieve_evidence(self, db:Session, message:StreamMessage, original_article_id: int):
        # Evaluate each input claim to get evidence matches, verdict, and confidence.
        # Keep one output row per input claim (do not merge by claim text).
        claim_results: List[Dict[str, Any]] = []
        evidence_claim_ids = []

        for input_claim in (message.all_claims or []):
            input_claim_evaluation = self._retrieve_evidence_for_claim(
                db=db,
                claim=input_claim,
                original_article_id=original_article_id,
            )
            self.logger.debug("EVIDENCE RETRIEVED")

            claim_results.append(input_claim_evaluation)

            evidence_claim_ids.extend([evidence_claim.get("claim_id") for evidence_claim in input_claim_evaluation.get("matches", [])])
        
        # Extend evidence claims into articles
        self.logger.debug("EXTENDING CLAIMS INTO ARTICLES")
        related_articles = extend_evidence_claims_into_articles(
            db=db,
            claim_ids=evidence_claim_ids,
            current_article_id=original_article_id
        )
        
        self.logger.info(
            "Retrieval matches on job uid=%s claim_matches=%s",
            # message.data.header.uid,
            message.header.uid,
            len(evidence_claim_ids),
        )

        return claim_results, related_articles
    
    def _save_job_into_postgres(self, db:Session, message:StreamMessage):
        job_dto = UpdateJob(message.header.id, message.header.uid, JobStatus.COMPLETE, message.stage_timestamps)
        job_entry = finalise_and_complete_job(db, job_dto)        
        self.logger.info(
            "DB write result job=%s",
            job_entry
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
            processed_message:StreamMessage = self._process_message(message)
                       
            payload = processed_message.retrieval_results or {}
            
            new_id = "END OF PIPELINE"
            if message.type == JobType.USER:
                self.hash_store.set(message.uid, payload)
                new_id = message.uid
                matches = payload.get("matches") or []
                related_articles = payload.get("related_articles") or []
                self.logger.info(
                    "Stored retrieval result for job_uid=%s:\\n"
                    "  save_data_result keys: %s\\n"
                    "  save_job_result keys: %s\\n"
                    "  matches: %d\\n"
                    "  related_articles: %d",
                    message.uid,
                    list(payload.get("save_data_result", {}).keys()) if payload.get("save_data_result") else [],
                    list(payload.get("save_job_result", {}).keys()) if payload.get("save_job_result") else [],
                    len(matches),
                    len(related_articles)
                )

            if self.is_cut_and_paste_mode:
                self.message_consumer.acknowledge_and_delete(message.stream, message.redis_id)
            else:
                self.message_consumer.acknowledge(message.stream, message.redis_id)
                
            return message.redis_id, new_id #id in hashset

        except Exception as e:
            # Catch any exception, including ProcessingError, and route to failure.
            self._handle_failure(message, e)
            # Raise it again so as_completed knows the future failed
            raise
	
    def _process_batch_sequentially(self, raw_messages: List[Dict[str, Any]]) -> None:
        self.logger.info(f"Fetched {len(raw_messages)} messages. Processing...")

        stream_messages: List[StreamMessage] = [msg for m in raw_messages if (msg := self._parse_message(m))]
        ack_count = 0
        failure_count = 0
        
        for message in stream_messages:
            try:
                processed_message = self._process_message(message)
                
                payload = processed_message.retrieval_results or {}
                new_id = "END OF PIPELINE"
                if message.type == JobType.USER:
                    self.hash_store.set(message.uid, payload)
                    new_id = message.uid
                    matches = payload.get("matches") or []
                    related_articles = payload.get("related_articles") or []
                    self.logger.info(
                        "Stored retrieval result for job_uid=%s:\n"
                        "  save_data_result keys: %s\n"
                        "  save_job_result keys: %s\n"
                        "  matches: %d\n"
                        "  related_articles: %d",
                        message.uid,
                        list(payload.get("save_data_result", {}).keys()) if payload.get("save_data_result") else [],
                        list(payload.get("save_job_result", {}).keys()) if payload.get("save_job_result") else [],
                        len(matches),
                        len(related_articles)
                    )
                
                if self.is_cut_and_paste_mode:
                    self.message_consumer.acknowledge_and_delete(message.stream, message.redis_id)
                else:
                    self.message_consumer.acknowledge(message.stream, message.redis_id)
                
                self.logger.debug(f"Successfully published Msg {message.redis_id} -> {new_id} in hashset")
                ack_count+=1

            except Exception as e:
                self.logger.warning(f"Failed to publish message {message.redis_id}. See previous error logs for details.")
                self._handle_failure(message, e)
                failure_count+=1
 
        
        if ack_count > 0:
            self.logger.info(f"Successfully saved and acknowledged {ack_count} messages.")
        
        if failure_count > 0:
            # The logging for this is handled inside _handle_failure, 
            # but a summary log is good practice.
            self.logger.info(f"Handled {failure_count} failed messages by sending to failure stream.")

    def _process_batch_concurrently(self, executor: ThreadPoolExecutor, raw_messages: List[Dict[str,Any]]):
        self.logger.info(f"Fetched {len(raw_messages)} messages. Processing...")
        stream_messages = [msg for m in raw_messages if (msg := self._parse_message(m))]

        future_to_message = {
            executor.submit(self._process_and_publish_worker, msg): msg for msg in stream_messages
        }

        for future in as_completed(future_to_message):
            original_message = future_to_message[future] 

            try:
                old_redis_id, new_redis_id = future.result() 
                self.logger.debug(f"Successfully published Msg {old_redis_id} -> {new_redis_id} in hashset")
            except Exception:
                self.logger.warning(f"A worker for message {original_message.redis_id} failed. See previous error logs for details.")

    def _process_message(self, message: StreamMessage) -> StreamMessage:
        
        # one db session to make sure the entire thing is 1 transcation
        # just raise an exception and it will roll back everything
        with get_db_transaction() as db:
            save_data_result = self._save_data_into_postgres(db, message)
            if message.type == JobType.BACKGROUND:
                return message
            
            #continue to retrieval
            # retrieval stuff is only for user jobs
            original_article_id = save_data_result.get("article_entry_id") or 0
            claim_evidence_matches, related_articles = self._retrieve_evidence(db, message, original_article_id)
            save_job_result = self._save_job_into_postgres(db, message)
            
            # message.set_retrieval_result(
            #     RetrievalResult(
            #         save_data_result,
            #         save_job_result,
            #         claim_evidence_matches,
            #         related_articles
            #     )
            # )
            retrieval_result = RetrievalResult(
            save_data_result,
            save_job_result,
            claim_evidence_matches,
            related_articles
            )
            # hashstore inside transaction block — if this fails, DB rolls back too
            # if message.type == JobType.USER:
            #     self.hash_store.set(message.uid, retrieval_result.__dict__)
        
            message.set_retrieval_result(retrieval_result)
            return message
                    
