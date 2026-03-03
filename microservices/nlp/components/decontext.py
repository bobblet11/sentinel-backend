import logging
import re
import spacy
import torch
from typing import List, Optional
from rank_bm25 import BM25Okapi
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM, pipeline

# Local imports
from microservices.nlp.models.base import SentenceProcessor
from common.models.api.redis_models import Article, NLPOptions, NLPResult, SentenceScore
from microservices.nlp.config import (
    QG_MODEL, QA_MODEL, GEN_MODEL,
    BM25_TOP_K, QA_SCORE_THRESHOLD,
    BERT_MAX_LENGTH, DECONTEXT_MAX_GEN_LENGTH,
    DECONTEXT_MAX_UNITS, DECONTEXT_REWRITE_RATIO,
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

    def __init__(self, use_gpu: bool = True, nlp=None):
        self.device    = "cuda" if use_gpu and torch.cuda.is_available() else "cpu"
        self.device_id = 0 if self.device == "cuda" else -1
        use_fp16       = self.device == "cuda"

        logger.info(f"Decontextualizer: Initializing on {self.device} (fp16={use_fp16})...")

        if nlp is not None:
            logger.info("Decontextualizer: Using shared spaCy model.")
            self.nlp = nlp
        else:
            try:
                self.nlp = spacy.load("en_core_web_sm")
            except OSError:
                logger.error("Decontextualizer: Run: python -m spacy download en_core_web_sm")
                raise

        # Question Generation model
        self.qg_tokenizer = AutoTokenizer.from_pretrained(QG_MODEL)
        self.qg_model = AutoModelForSeq2SeqLM.from_pretrained(
            QG_MODEL,
            torch_dtype=torch.float16 if use_fp16 else torch.float32,
        ).to(self.device)

        # Extractive QA pipeline — __call__ is (self, **kwargs) only;
        # no positional args or batch_size accepted at call time.
        self.qa_pipe = pipeline(
            "question-answering",
            model=QA_MODEL,
            device=self.device_id,
            torch_dtype=torch.float16 if use_fp16 else torch.float32,
        )

        # Generative rewrite model (FLAN-T5)
        self.gen_tokenizer = AutoTokenizer.from_pretrained(GEN_MODEL)
        self.gen_model = AutoModelForSeq2SeqLM.from_pretrained(
            GEN_MODEL,
            torch_dtype=torch.float16 if use_fp16 else torch.float32,
        ).to(self.device)

        logger.info("Decontextualizer: All models loaded successfully.")

    def _sanitize(self, text: str) -> str:
        """Strips model-prefixed label artifacts (e.g. 'false: ', 'entailment: ')."""
        return self._LABEL_RE.sub("", text).strip()

    def _generate_batch(self, prompts: List[str], tokenizer, model) -> List[str]:
        """Batched seq2seq generation with beam search."""
        if not prompts:
            return []
        inputs = tokenizer(
            prompts, return_tensors="pt", padding=True, truncation=True, max_length=BERT_MAX_LENGTH,
        ).to(self.device)
        with torch.no_grad():
            outputs = model.generate(
                **inputs, max_length=DECONTEXT_MAX_GEN_LENGTH, num_beams=4,
                repetition_penalty=2.5, early_stopping=True,
            )
        return [self._sanitize(tokenizer.decode(o, skip_special_tokens=True)) for o in outputs]

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
            return ""
        tokenized_corpus = [s.lower().split() for s in doc_sentences]
        bm25 = BM25Okapi(tokenized_corpus)
        scores = bm25.get_scores(query.lower().split())
        top_k = min(BM25_TOP_K, len(doc_sentences))
        top_indices = scores.argsort()[-top_k:][::-1]
        return " ".join(doc_sentences[i] for i in sorted(top_indices))

    def _process_sentence(
        self,
        sent_text: str,
        units: List[str],
        doc_sentences: List[str],
    ) -> Optional[str]:
        """
        Full three-stage processing for a single sentence:
        QG → BM25 retrieval → QA grounding → QA-to-declarative conversion.
        Returns a concatenated context string or None if no useful context found.
        """
        if not units:
            return None

        qg_prompts = [f"answer: {u} context: {sent_text}" for u in units]
        questions  = self._generate_batch(qg_prompts, self.qg_tokenizer, self.qg_model)

        qa_inputs = []
        for question in questions:
            evidence = self._bm25_retrieve(question, doc_sentences)
            qa_inputs.append({"question": question, "context": evidence or sent_text})

        try:
            # QuestionAnsweringPipeline.__call__ is (self, **kwargs) — no positional
            # args are accepted. Must call with explicit keyword arguments per input.
            qa_results = [
                self.qa_pipe(question=inp["question"], context=inp["context"])
                for inp in qa_inputs
            ]
        except Exception as e:
            logger.warning(f"Decontextualizer: QA batch failed — {e}")
            return None

        qa2d_prompts = [
            f"Convert to a declarative sentence: Q: {q} A: {r['answer']}"
            for q, r in zip(questions, qa_results)
            if r["score"] > QA_SCORE_THRESHOLD
        ]

        if not qa2d_prompts:
            return None

        try:
            context_sentences = self._generate_batch(qa2d_prompts, self.gen_tokenizer, self.gen_model)
        except Exception as e:
            logger.warning(f"Decontextualizer: QA2D batch failed — {e}")
            return None

        # Drop any output that FLAN-T5 returned as a question instead of a
        # declarative sentence (QA2D model failure mode).
        declarative_only = [s for s in context_sentences if s and not s.rstrip().endswith("?")]
        return " ".join(declarative_only) or None

    def run(
        self,
        article: Article,
        result: NLPResult,
        options: NLPOptions,
        sentences: List[SentenceScore],
    ) -> List[SentenceScore]:
        """
        Rewrites each sentence to be self-contained.
        Preserves original_text on the SentenceScore before overwriting text.
        Returns the updated local sentences list; does NOT write to result.
        """
        if not sentences:
            return []

        # Build flat list of article sentences for BM25 context retrieval
        doc_sentences = [
            s.strip()
            for s in re.split(r"(?<=[.!?])\s+", article.text or "")
            if len(s.strip()) > 10
        ]

        for sent_obj in sentences:
            cleaned_text = self._sanitize(sent_obj.text)
            if not cleaned_text:
                sent_obj.text = ""
                continue

            doc            = self.nlp(cleaned_text)
            units          = self._extract_units(doc)
            filtered_units = [u for u in units if len(u.split()) < 6][:DECONTEXT_MAX_UNITS]
            full_context   = self._process_sentence(cleaned_text, filtered_units, doc_sentences)

            if full_context:
                final_prompt = (
                    f"Rewrite the sentence to be self-contained by incorporating "
                    f"specific details from the context.\n"
                    f"Context: {full_context}\n"
                    f"Sentence: {cleaned_text}\n"
                    f"Rewrite:"
                )
                try:
                    rewrites = self._generate_batch(
                        [final_prompt], self.gen_tokenizer, self.gen_model
                    )
                    rewritten = rewrites[0] if rewrites else ""

                    # Quality gate: reject the rewrite if it
                    #   (a) is empty or unchanged,
                    #   (b) contains a question mark (leaked QG output), or
                    #   (c) is more than 2.5× the original length (hallucination)
                    max_len = int(len(cleaned_text) * DECONTEXT_REWRITE_RATIO)
                    if (rewritten
                            and rewritten.lower() != cleaned_text.lower()
                            and "?" not in rewritten
                            and len(rewritten) <= max_len):
                        sent_obj.original_text = cleaned_text
                        sent_obj.text = rewritten
                    else:
                        sent_obj.text = cleaned_text
                except Exception as e:
                    logger.warning(f"Decontextualizer: Final rewrite failed — {e}")
                    sent_obj.text = cleaned_text
            else:
                sent_obj.text = cleaned_text

        logger.info("Decontextualizer: Complete.")
        return sentences
