import logging
import re
import time
import spacy
import torch
from typing import List, Optional
from rank_bm25 import BM25Okapi
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM, AutoModelForQuestionAnswering

# Local imports
from microservices.nlp.models.base import SentenceProcessor
from microservices.nlp.components.device import DeviceConfig
from common.models.api.redis_models import Article, NLPOptions, NLPResult, SentenceScore
from microservices.nlp.config import (
    QG_MODEL, QA_MODEL, GEN_MODEL,
    BM25_TOP_K, QA_SCORE_THRESHOLD,
    BERT_MAX_LENGTH, DECONTEXT_MAX_GEN_LENGTH,
    DECONTEXT_MAX_UNITS, DECONTEXT_REWRITE_RATIO,
    DECONTEXT_QG_BATCH_SIZE,
    DECONTEXT_QA_BATCH_SIZE,
    DECONTEXT_GEN_BATCH_SIZE,
)

logger = logging.getLogger(__name__)


class Decontextualizer(SentenceProcessor):
    """
    MODULAR DECONTEXTUALIZER LAYER

    Rewrites each extracted sentence to be fully self-contained by resolving
    pronouns, ellipsis, and implicit references using a three-stage process:

    Strategies Applied:
    1.  Unit Extraction (spaCy): Identifies ambiguous elements within a sentence —
        named entities, pronouns (PRON), noun chunks, and root verb phrases — that
        require external context to be interpretable.
    2.  Question Generation (mrm8488/t5-base-finetuned-question-generation-ap):
        For each ambiguous unit, a clarifying question is generated using the
        prompt pattern "answer: <unit> context: <sentence>".
    3.  BM25 Evidence Retrieval: Each question is grounded against the full article
        text using BM25Okapi (top-k=3 sentences) to identify the most relevant
        supporting context passage.
    4.  QA Grounding (deepset/roberta-base-squad2): The question is answered using
        the BM25-retrieved evidence. Answers below a confidence threshold of 0.35
        are discarded to avoid hallucinations.
    5.  QA-to-Declarative (google/flan-t5-base): Valid Q-A pairs are converted into
        standalone declarative sentences via the prompt:
        "Convert to a declarative sentence: Q: <q> A: <answer>".
    6.  Final Rewrite (google/flan-t5-base): All declarative context sentences are
        concatenated and fed into a final rewrite prompt, instructing the model to
        incorporate specific details while preserving the original's meaning.
    7.  Sanitization: A regex strips any label prefixes (e.g. "false:", "entailment:")
        that seq2seq models sometimes prepend to their output.

    Batch Sizes: QG uses gen_batch_size=8, QA uses qa_batch_size=8.
    BM25 top-k: 3 sentences per query.
    QA score threshold: 0.35 (answers below this are skipped).
    Max generation length: 128 tokens.

    Accepts and returns a local sentences list; does NOT write to result.
    """

    _LABEL_RE = re.compile(
        r"^(false|true|fake|entailment|neutral|contradiction)\b[\s:,]*",
        flags=re.IGNORECASE,
    )

    def __init__(self, device_config: DeviceConfig, nlp=None):
        self.device = device_config.device
        self.device_id = device_config.device_id

        logger.info(f"Decontextualizer: Initializing on {self.device} (fp16={device_config.use_fp16})...")

        if nlp is not None:
            logger.info("Decontextualizer: Using shared spaCy model.")
            self.nlp = nlp
        else:
            try:
                self.nlp = spacy.load("en_core_web_sm")
            except OSError:
                logger.error("Decontextualizer: Run: python -m spacy download en_core_web_sm")
                raise

        _dtype = device_config.dtype
        # Disable low_cpu_mem_usage to prevent accelerate from initialising
        # weights on the meta device (which breaks .to() and .generate()).
        _load_kw = dict(dtype=_dtype, low_cpu_mem_usage=False)

        # Question Generation model
        self.qg_tokenizer = AutoTokenizer.from_pretrained(QG_MODEL)
        self.qg_model = AutoModelForSeq2SeqLM.from_pretrained(
            QG_MODEL, **_load_kw,
        ).to(self.device)

        # Extractive QA model
        self.qa_tokenizer = AutoTokenizer.from_pretrained(QA_MODEL)
        self.qa_model = AutoModelForQuestionAnswering.from_pretrained(
            QA_MODEL, **_load_kw,
        ).to(self.device)

        # Generative rewrite model (FLAN-T5)
        self.gen_tokenizer = AutoTokenizer.from_pretrained(GEN_MODEL)
        self.gen_model = AutoModelForSeq2SeqLM.from_pretrained(
            GEN_MODEL, **_load_kw,
        ).to(self.device)

        logger.info("Decontextualizer: All models loaded successfully.")

    def _sanitize(self, text: str) -> str:
        """Strips model-prefixed label artifacts (e.g. 'false: ', 'entailment: ')."""
        return self._LABEL_RE.sub("", text).strip()

    def _generate_batch(
        self,
        prompts: List[str],
        tokenizer,
        model,
        batch_size: int = 8,
        label: str = "gen",
    ) -> List[str]:
        """
        Chunked batched seq2seq generation with beam search.
        Processes prompts in chunks of `batch_size` to avoid GPU OOM on large batches.
        Logs per-chunk progress so callers can see the batch is alive.
        """
        if not prompts:
            return []
        total_prompts = len(prompts)
        total_chunks  = (total_prompts + batch_size - 1) // batch_size
        results: List[str] = []
        for chunk_idx, chunk_start in enumerate(range(0, total_prompts, batch_size), start=1):
            chunk     = prompts[chunk_start : chunk_start + batch_size]
            done_so_far = chunk_start + len(chunk)
            t0 = time.perf_counter()
            inputs = tokenizer(
                chunk, return_tensors="pt", padding=True, truncation=True,
                max_length=BERT_MAX_LENGTH,
            ).to(self.device)
            with torch.no_grad():
                outputs = model.generate(
                    **inputs, max_length=DECONTEXT_MAX_GEN_LENGTH, num_beams=4,
                    repetition_penalty=2.5, early_stopping=True,
                )
            results.extend(
                self._sanitize(tokenizer.decode(o, skip_special_tokens=True))
                for o in outputs
            )
            elapsed = time.perf_counter() - t0
            logger.info(
                f"Decontextualizer [{label}] chunk {chunk_idx}/{total_chunks} "
                f"— {done_so_far}/{total_prompts} prompts done ({elapsed:.1f}s)"
            )
        return results

    def _qa_infer(self, question: str, context: str) -> dict:
        """
        Single extractive QA inference using AutoModelForQuestionAnswering.
        Returns {"score": float, "answer": str} to match the old pipeline output.
        """
        inputs = self.qa_tokenizer(
            question,
            context,
            return_tensors="pt",
            truncation=True,
            max_length=BERT_MAX_LENGTH,
            padding=True,
        ).to(self.device)
        with torch.no_grad():
            outputs = self.qa_model(**inputs)
        start_probs = torch.softmax(outputs.start_logits[0], dim=-1)
        end_probs   = torch.softmax(outputs.end_logits[0],   dim=-1)
        seq_len     = start_probs.size(0)
        max_span    = 50  # cap answer span at 50 tokens
        # Build score matrix; zero-out invalid spans (end < start or too long)
        score_matrix = torch.outer(start_probs, end_probs)
        mask = torch.tril(torch.ones(seq_len, seq_len, device=self.device))
        score_matrix = score_matrix * mask
        for i in range(seq_len):
            if i + max_span < seq_len:
                score_matrix[i, i + max_span :] = 0.0
        best_idx    = score_matrix.argmax()
        best_start  = (best_idx // seq_len).item()
        best_end    = (best_idx % seq_len).item()
        best_score  = score_matrix[best_start, best_end].item()
        answer_ids  = inputs["input_ids"][0][best_start : best_end + 1]
        answer      = self.qa_tokenizer.decode(answer_ids, skip_special_tokens=True)
        return {"score": best_score, "answer": answer}

    def _qa_batch(self, inputs: List[dict], batch_size: int) -> List[dict]:
        """
        Chunked extractive QA inference.
        Iterates in chunks and logs progress.
        """
        if not inputs:
            return []
        total        = len(inputs)
        total_chunks = (total + batch_size - 1) // batch_size
        results: List[dict] = []
        for chunk_idx, chunk_start in enumerate(range(0, total, batch_size), start=1):
            chunk       = inputs[chunk_start : chunk_start + batch_size]
            done_so_far = chunk_start + len(chunk)
            t0 = time.perf_counter()
            for inp in chunk:
                results.append(self._qa_infer(inp["question"], inp["context"]))
            elapsed = time.perf_counter() - t0
            logger.info(
                f"Decontextualizer [QA] chunk {chunk_idx}/{total_chunks} "
                f"\u2014 {done_so_far}/{total} inputs done ({elapsed:.1f}s)"
            )
        return results

    def _extract_units(self, doc) -> List[str]:
        """
        Extracts ambiguous referential units from a spaCy Doc:
        named entities, pronouns, compact noun chunks, and root verb phrases.
        """
        units: List[str] = []
        for ent in doc.ents:
            units.append(ent.text)
        for token in doc:
            if token.pos_ == "PRON":
                units.append(token.text)
        for chunk in doc.noun_chunks:
            if len(chunk.text.split()) < 5:
                units.append(chunk.text)
        for token in doc:
            if token.pos_ == "VERB" and token.dep_ in ("ROOT", "relcl", "advcl", "xcomp"):
                phrase_tokens = [token] + [
                    c for c in token.children
                    if c.dep_ in ("dobj", "prt", "attr") and c.i < token.i + 4
                ]
                phrase_tokens.sort(key=lambda t: t.i)
                phrase = " ".join(t.text for t in phrase_tokens)
                if phrase:
                    units.append(phrase)
        return [u for u in set(units) if len(u.split()) < 6 and len(u) > 1]

    def _bm25_retrieve(self, query: str, doc_sentences: List[str]) -> str:
        """BM25 sparse retrieval over article sentences to find the most relevant evidence."""
        if not doc_sentences:
            logger.debug(f"Decontextualizer [BM25] No doc_sentences available for query: {query[:60]}")
            return ""
        tokenized_corpus = [s.lower().split() for s in doc_sentences]
        bm25 = BM25Okapi(tokenized_corpus)
        scores = bm25.get_scores(query.lower().split())
        top_k = min(BM25_TOP_K, len(doc_sentences))
        top_indices = scores.argsort()[-top_k:][::-1]
        top_scores = [scores[i] for i in top_indices]
        evidence = " ".join(doc_sentences[i] for i in sorted(top_indices))
        logger.debug(
            f"Decontextualizer [BM25] Query: {query[:50]}... | "
            f"Top scores: {top_scores} | Evidence len: {len(evidence)}"
        )
        return evidence

    def run(
        self,
        article: Article,
        result: NLPResult,
        options: NLPOptions,
        sentences: List[SentenceScore],
    ) -> List[SentenceScore]:
        """
        Rewrites each sentence to be self-contained using fully batched inference.

        All four model passes (QG / QA / QA2D / rewrite) are batched across
        every sentence in a single forward sweep instead of looping per-sentence.
        Sentence-boundary bookkeeping uses (start, end) slice tuples so results
        can be mapped back after each global batch call.

        Preserves original_text on the SentenceScore before overwriting text.
        Returns the updated local sentences list; does NOT write to result.
        """
        if not sentences:
            return []

        n = len(sentences)

        # BM25 corpus: all article sentences used as evidence for QA
        doc_sentences = [
            s.strip()
            for s in re.split(r"(?<=[.!?])\s+", article.text or "")
            if len(s.strip()) > 10
        ]

        # ── Phase 1: batch spaCy parse ─────────────────────────────────────
        logger.info(f"Decontextualizer: Phase 1 — spaCy batch parse ({n} sentences)...")
        t_phase = time.perf_counter()
        texts = [self._sanitize(s.text) for s in sentences]
        docs  = list(self.nlp.pipe(texts))
        logger.info(f"Decontextualizer: Phase 1 done ({time.perf_counter() - t_phase:.1f}s)")

        # ── Phase 2: extract units; build flat QG prompt list ─────────────
        all_qg_prompts: List[str]  = []
        sent_qg_slices: List[tuple] = []   # (start, end) into all_qg_prompts
        units_per_sent: List[List[str]] = []  # for debugging

        for text, doc in zip(texts, docs):
            start = len(all_qg_prompts)
            if text:
                units = [
                    u for u in self._extract_units(doc) if len(u.split()) < 6
                ][:DECONTEXT_MAX_UNITS]
                units_per_sent.append(units)
                all_qg_prompts.extend(f"answer: {u} context: {text}" for u in units)
                logger.debug(
                    f"Decontextualizer [Phase 2] Sentence: {text[:60]}... | "
                    f"Extracted {len(units)} units: {units}"
                )
            else:
                units_per_sent.append([])
            sent_qg_slices.append((start, len(all_qg_prompts)))

        # ── Phase 3: batch Question Generation ────────────────────────────
        logger.info(
            f"Decontextualizer: Phase 3 — QG batch ({len(all_qg_prompts)} prompts "
            f"across {n} sentences, chunk_size={DECONTEXT_QG_BATCH_SIZE})..."
        )
        t_phase = time.perf_counter()
        all_questions = self._generate_batch(
            all_qg_prompts, self.qg_tokenizer, self.qg_model,
            batch_size=DECONTEXT_QG_BATCH_SIZE, label="QG",
        )
        logger.info(f"Decontextualizer: Phase 3 done ({time.perf_counter() - t_phase:.1f}s)")

        # ── Phase 4: BM25 retrieval → flat QA input list ──────────────────
        all_qa_inputs: List[dict]   = []
        sent_qa_slices: List[tuple]  = []   # (start, end) into all_qa_inputs

        for i, (qg_start, qg_end) in enumerate(sent_qg_slices):
            qa_start = len(all_qa_inputs)
            for question in all_questions[qg_start:qg_end]:
                evidence = self._bm25_retrieve(question, doc_sentences)
                all_qa_inputs.append(
                    {"question": question, "context": evidence or texts[i]}
                )
            sent_qa_slices.append((qa_start, len(all_qa_inputs)))

        # ── Phase 5: batch Extractive QA ──────────────────────────────────
        logger.info(
            f"Decontextualizer: Phase 5 — QA batch ({len(all_qa_inputs)} inputs, "
            f"chunk_size={DECONTEXT_QA_BATCH_SIZE})..."
        )
        t_phase = time.perf_counter()
        if all_qa_inputs:
            all_qa_results: List[dict] = self._qa_batch(
                all_qa_inputs, batch_size=DECONTEXT_QA_BATCH_SIZE
            )
        else:
            all_qa_results = []
        logger.info(f"Decontextualizer: Phase 5 done ({time.perf_counter() - t_phase:.1f}s)")

        # ── Phase 6: build QA2D prompt list ───────────────────────────────
        all_qa2d_prompts: List[str]   = []
        sent_qa2d_slices: List[tuple]  = []   # (start, end) into all_qa2d_prompts
        qa_filtering_stats: List[dict] = []  # for debugging

        for sent_idx, ((qg_start, qg_end), (qa_start, qa_end)) in enumerate(zip(
            sent_qg_slices, sent_qa_slices
        )):
            qa2d_start = len(all_qa2d_prompts)
            passed_count = 0
            failed_count = 0
            
            for u_idx, (q, r) in enumerate(zip(
                all_questions[qg_start:qg_end], all_qa_results[qa_start:qa_end]
            )):
                if r["score"] > QA_SCORE_THRESHOLD:
                    all_qa2d_prompts.append(
                        f"Convert to a declarative sentence: Q: {q} A: {r['answer']}"
                    )
                    passed_count += 1
                else:
                    failed_count += 1
                    logger.debug(
                        f"Decontextualizer [Phase 6] Sentence {sent_idx} unit {u_idx}: "
                        f"Q: {q[:50]}... | Score {r['score']:.3f} < threshold {QA_SCORE_THRESHOLD} → FILTERED"
                    )
            
            qa_filtering_stats.append({"passed": passed_count, "failed": failed_count})
            if passed_count > 0 or failed_count > 0:
                logger.debug(
                    f"Decontextualizer [Phase 6] Sentence {sent_idx}: "
                    f"{passed_count} Q-A pairs passed threshold, {failed_count} filtered"
                )
            sent_qa2d_slices.append((qa2d_start, len(all_qa2d_prompts)))

        # ── Phase 7: batch QA-to-Declarative ──────────────────────────────
        logger.info(
            f"Decontextualizer: Phase 7 — QA2D batch ({len(all_qa2d_prompts)} prompts, "
            f"chunk_size={DECONTEXT_GEN_BATCH_SIZE})..."
        )
        t_phase = time.perf_counter()
        all_qa2d_results = self._generate_batch(
            all_qa2d_prompts, self.gen_tokenizer, self.gen_model,
            batch_size=DECONTEXT_GEN_BATCH_SIZE, label="QA2D",  # flan-t5-base
        )
        logger.info(f"Decontextualizer: Phase 7 done ({time.perf_counter() - t_phase:.1f}s)")

        # ── Phase 8: build final rewrite prompt list ───────────────────────
        all_rewrite_prompts: List[str]    = []
        sent_rewrite_idx: List[Optional[int]] = []  # index into all_rewrite_prompts, or None

        for i, (qa2d_start, qa2d_end) in enumerate(sent_qa2d_slices):
            declarative = [
                s for s in all_qa2d_results[qa2d_start:qa2d_end]
                if s and not s.rstrip().endswith("?")
            ]
            if declarative and texts[i]:
                full_context = " ".join(declarative)
                final_prompt = (
                    f"Rewrite the sentence to be self-contained by incorporating "
                    f"specific details from the context.\n"
                    f"Context: {full_context}\n"
                    f"Sentence: {texts[i]}\n"
                    f"Rewrite:"
                )
                sent_rewrite_idx.append(len(all_rewrite_prompts))
                all_rewrite_prompts.append(final_prompt)
            else:
                sent_rewrite_idx.append(None)

        # ── Phase 9: batch final rewrite ──────────────────────────────────
        logger.info(
            f"Decontextualizer: Phase 9 — Rewrite batch ({len(all_rewrite_prompts)} prompts, "
            f"chunk_size={DECONTEXT_GEN_BATCH_SIZE})..."
        )
        t_phase = time.perf_counter()
        all_rewrites = self._generate_batch(
            all_rewrite_prompts, self.gen_tokenizer, self.gen_model,
            batch_size=DECONTEXT_GEN_BATCH_SIZE, label="Rewrite",  # flan-t5-base
        )
        logger.info(f"Decontextualizer: Phase 9 done ({time.perf_counter() - t_phase:.1f}s)")

        # ── Phase 10: apply results back to SentenceScore objects ──────────
        _AMBIGUOUS_PRONOUNS = {"he", "she", "they", "it", "his", "her", "their", "its", "him", "them"}

        def _has_unresolved_pronouns(original: str, rewrite: str) -> bool:
            """Return True if the rewrite still contains a pronoun that was present in the original."""
            orig_words = set(original.lower().split())
            rw_words = set(rewrite.lower().split())
            orig_pronouns = orig_words & _AMBIGUOUS_PRONOUNS
            return bool(orig_pronouns & rw_words)

        rejection_summary = {"empty": 0, "unchanged": 0, "has_question": 0, "too_long": 0, "has_pronoun": 0, "accepted": 0}

        for i, sent_obj in enumerate(sentences):
            text = texts[i]
            if not text:
                sent_obj.text = ""
                continue

            rw_idx = sent_rewrite_idx[i]
            if rw_idx is not None:
                rewritten = all_rewrites[rw_idx]
                max_len   = int(len(text) * DECONTEXT_REWRITE_RATIO)

                # Quality gate: reject if empty, unchanged, contains "?", too long, or pronouns unresolved
                rejection_reason = None
                if not rewritten:
                    rejection_reason = "empty"
                    rejection_summary["empty"] += 1
                elif rewritten.lower() == text.lower():
                    rejection_reason = "unchanged"
                    rejection_summary["unchanged"] += 1
                elif "?" in rewritten:
                    rejection_reason = "has_question"
                    rejection_summary["has_question"] += 1
                elif len(rewritten) > max_len:
                    rejection_reason = "too_long"
                    rejection_summary["too_long"] += 1
                elif _has_unresolved_pronouns(text, rewritten):
                    rejection_reason = "has_pronoun"
                    rejection_summary["has_pronoun"] += 1

                if rejection_reason:
                    logger.debug(
                        f"Decontextualizer [Phase 10] Sentence {i}: Rewrite REJECTED ({rejection_reason}) | "
                        f"Original: {text[:50]}... | "
                        f"Rewritten: {rewritten[:50]}... | "
                        f"Len: {len(rewritten)} vs max {max_len}"
                    )
                    sent_obj.text = text
                else:
                    logger.debug(
                        f"Decontextualizer [Phase 10] Sentence {i}: Rewrite ACCEPTED | "
                        f"Original: {text[:50]}... → Rewritten: {rewritten[:50]}..."
                    )
                    sent_obj.original_text = text
                    sent_obj.text          = rewritten
                    rejection_summary["accepted"] += 1
            else:
                logger.debug(
                    f"Decontextualizer [Phase 10] Sentence {i}: No QA2D results, keeping original"
                )
                sent_obj.text = text

        logger.info(
            f"Decontextualizer [Phase 10 Summary]: "
            f"Accepted={rejection_summary['accepted']}, "
            f"Rejected (empty={rejection_summary['empty']}, "
            f"unchanged={rejection_summary['unchanged']}, "
            f"has_?={rejection_summary['has_question']}, "
            f"too_long={rejection_summary['too_long']}, "
            f"has_pronoun={rejection_summary['has_pronoun']})"
        )

        logger.info("Decontextualizer: Complete.")
        return sentences