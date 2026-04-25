# Citations & Credits for Final Report

All models, libraries, datasets, and infrastructure tools used in Sentinel Backend that require citation or acknowledgement in an academic paper.

---

## A. Pre-trained Models (HuggingFace) — Require In-Text Citation

These must be cited wherever the corresponding NLP component is described in the Methodology section.

---

### A1. Named Entity Recognition — `dslim/bert-base-NER-uncased`
- **Used in**: `EntityRecognizer` component (`microservices/nlp/components/ner.py`)
- **Pipeline stage**: NLP → token classification
- **HuggingFace URL**: https://huggingface.co/dslim/bert-base-NER-uncased
- **Underlying model**: BERT-base fine-tuned on CoNLL-2003 (4-class NER: PER, ORG, LOC, MISC)
- **Original paper to cite**:
  > Devlin, J., Chang, M.-W., Lee, K., & Toutanova, K. (2019). BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding. *NAACL-HLT 2019*. https://arxiv.org/abs/1810.04805
- **Also cite the CoNLL-2003 dataset**:
  > Tjong Kim Sang, E. F., & De Meulder, F. (2003). Introduction to the CoNLL-2003 shared task: Language-independent named entity recognition. *CoNLL-2003*. https://aclanthology.org/W03-0419

---

### A2. Sentence Embeddings — `sentence-transformers/all-mpnet-base-v2`
- **Used in**: `Embedder` component (`microservices/nlp/components/embedder.py`) and `TopicClassifier`
- **Pipeline stage**: NLP → semantic embedding (768-dim vectors stored in pgvector)
- **HuggingFace URL**: https://huggingface.co/sentence-transformers/all-mpnet-base-v2
- **Library**: `sentence-transformers`
- **Paper to cite**:
  > Reimers, N., & Gurevych, I. (2019). Sentence-BERT: Sentence Embeddings using Siamese BERT-Networks. *EMNLP 2019*. https://arxiv.org/abs/1908.10084
- **Also cite the underlying MPNet model**:
  > Song, K., Tan, X., Qin, T., Lu, J., & Liu, T.-Y. (2020). MPNet: Masked and Permuted Pre-training for Language Understanding. *NeurIPS 2020*. https://arxiv.org/abs/2004.09297

---

### A3. Political Bias Classification — `premsa/political-bias-prediction-allsides-BERT`
- **Used in**: `BiasDetector` component (`microservices/nlp/components/bias.py`)
- **Pipeline stage**: NLP → text classification (Left / Center / Right)
- **HuggingFace URL**: https://huggingface.co/premsa/political-bias-prediction-allsides-BERT
- **Based on**: BERT fine-tuned on AllSides Media Bias Ratings dataset
- **Paper/source to cite** (AllSides dataset):
  > Baly, R., Da San Martino, G., Glass, J., & Nakov, P. (2020). We Can Detect Your Bias: Predicting the Political Ideology of News Articles. *EMNLP 2020*. https://aclanthology.org/2020.emnlp-main.404
- **Note**: The `premsa/` model itself has no accompanying paper — cite via HuggingFace model card URL and the BERT paper (Devlin et al., 2019).

---

### A4. Sentiment Analysis — `cardiffnlp/twitter-roberta-base-sentiment-latest`
- **Used in**: `BiasDetector` component (`microservices/nlp/components/bias.py`)
- **Pipeline stage**: NLP → sentiment (Positive / Neutral / Negative)
- **HuggingFace URL**: https://huggingface.co/cardiffnlp/twitter-roberta-base-sentiment-latest
- **Paper to cite**:
  > Barbieri, F., Camacho-Collados, J., Espinosa Anke, L., & Neves, L. (2020). TweetEval: Unified Benchmark and Comparative Evaluation for Tweet Classification. *EMNLP 2020 Findings*. https://arxiv.org/abs/2010.12421
- **Underlying model (RoBERTa)**:
  > Liu, Y., et al. (2019). RoBERTa: A Robustly Optimized BERT Pretraining Approach. https://arxiv.org/abs/1907.11692

---

### A5. Check-Worthiness Filter — `whispAI/ClaimBuster-DeBERTaV2`
- **Used in**: `CheckWorthinessFilter` component (`microservices/nlp/components/checkworthy.py`)
- **Pipeline stage**: NLP → text classification (claim vs non-claim)
- **HuggingFace URL**: https://huggingface.co/whispAI/ClaimBuster-DeBERTaV2
- **Based on**: ClaimBuster system, fine-tuned DeBERTa-v2
- **Paper to cite** (ClaimBuster):
  > Hassan, N., Arslan, F., Li, C., & Tremayne, M. (2017). Toward Automated Fact-Checking: Detecting Check-worthy Factual Claims by ClaimBuster. *KDD 2017*. https://dl.acm.org/doi/10.1145/3097983.3098131
- **Also cite DeBERTa**:
  > He, P., Liu, X., Gao, J., & Chen, W. (2021). DeBERTa: Decoding-enhanced BERT with Disentangled Attention. *ICLR 2021*. https://arxiv.org/abs/2006.03654

---

### A6. NLI / Claim Deduplication — `cross-encoder/nli-distilroberta-base`
- **Used in**: `CentralityScorer` / sentence extraction (`microservices/nlp/components/sentenceextract.py`)
- **Pipeline stage**: NLP → cross-encoder NLI for redundant claim filtering
- **HuggingFace URL**: https://huggingface.co/cross-encoder/nli-distilroberta-base
- **Paper to cite** (DistilRoBERTa / cross-encoders):
  > Sanh, V., et al. (2019). DistilBERT, a distilled version of BERT: smaller, faster, cheaper and lighter. *NeurIPS 2019 Workshop*. https://arxiv.org/abs/1910.01108
  > Reimers, N., & Gurevych, I. (2019). Sentence-BERT (cross-encoder architecture). Same citation as A2.

---

### A7. NLI for Retrieval — `typeform/distilbert-base-uncased-mnli`
- **Used in**: Retrieval layer NLI scoring (`microservices/retrieval_layer/retrieval/nli.py`)
- **Pipeline stage**: Retrieval → claim-vs-stored-claim entailment scoring
- **HuggingFace URL**: https://huggingface.co/typeform/distilbert-base-uncased-mnli
- **Based on**: DistilBERT fine-tuned on MultiNLI
- **Paper to cite**:
  > Williams, A., Nangia, N., & Bowman, S. (2018). A Broad-Coverage Challenge Corpus for Sentence Understanding through Inference (MultiNLI). *NAACL 2018*. https://arxiv.org/abs/1704.05426
  > Sanh, V., et al. (2019). DistilBERT. https://arxiv.org/abs/1910.01108

---

### A8. BERT Sentence Scoring — `bert-base-uncased`
- **Used in**: Centrality/sentence extraction scoring (`microservices/nlp/components/sentenceextract.py`)
- **Pipeline stage**: NLP → sentence importance scoring via BERT CLS embeddings
- **HuggingFace URL**: https://huggingface.co/google-bert/bert-base-uncased
- **Paper to cite**:
  > Devlin, J., Chang, M.-W., Lee, K., & Toutanova, K. (2019). BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding. *NAACL 2019*. https://arxiv.org/abs/1810.04805

---

### A9. Question Generation — `Salesforce/mixqg-base`
- **Used in**: `Decontextualizer` (`microservices/nlp/components/decontext.py`)
- **Active in**: **GPU deployment (production default — `NLP_GPU_ENABLE_DECONTEXTUALIZATION=true`)**; disabled on CPU-only instances
- **HuggingFace URL**: https://huggingface.co/Salesforce/mixqg-base
- **Paper to cite**:
  > Murakhovs'ka, L., et al. (2022). MixQG: Neural Question Generation with Mixed Answer Types. *NAACL 2022 Findings*. https://arxiv.org/abs/2110.03888

---

### A10. QA Grounding — `deepset/roberta-base-squad2`
- **Used in**: `Decontextualizer` (`microservices/nlp/components/decontext.py`)
- **Active in**: **GPU deployment (production default)**; disabled on CPU-only instances
- **HuggingFace URL**: https://huggingface.co/deepset/roberta-base-squad2
- **Paper to cite** (SQuAD 2.0):
  > Rajpurkar, P., et al. (2018). Know What You Don't Know: Unanswerable Questions for SQuAD. *ACL 2018*. https://arxiv.org/abs/1806.03822

---

### A11. Text Generation / Claim Rewriting — `google/flan-t5-base`
- **Used in**: `Decontextualizer` (`microservices/nlp/components/decontext.py`) — QA-to-Declarative (QA2D) and claim rewrite phases
- **Active in**: **GPU deployment (production default)**; disabled on CPU-only instances
- **HuggingFace URL**: https://huggingface.co/google/flan-t5-base
- **Paper to cite**:
  > Chung, H. W., et al. (2022). Scaling Instruction-Finetuned Language Models (FLAN-T5). *arXiv*. https://arxiv.org/abs/2210.11416

---

## B. NLP Frameworks & Libraries — Require Citation or Acknowledgement

---

### B1. HuggingFace Transformers
- **Used for**: Loading all transformer-based models (A1–A11) via `AutoModel`, `AutoTokenizer`, `pipeline()`
- **Version in use**: `transformers` (pinned via NLP Dockerfile)
- **Paper to cite**:
  > Wolf, T., et al. (2020). Transformers: State-of-the-Art Natural Language Processing. *EMNLP 2020 (demo)*. https://aclanthology.org/2020.emnlp-demos.6

---

### B2. Sentence-Transformers Library
- **Used for**: Loading `all-mpnet-base-v2` embeddings
- **Citation**: Same as A2 (Reimers & Gurevych, 2019)
- **Library URL**: https://www.sbert.net

---

### B3. spaCy — `en_core_web_sm`
- **Used in**: `Preprocessor`, `ClaimExtraction`, `Decontextualizer` for tokenization, sentence splitting, POS tagging
- **Model**: `en_core_web_sm` (small English pipeline)
- **Citation**:
  > Honnibal, M., Montani, I., Van Landeghem, S., & Boyd, A. (2020). spaCy: Industrial-strength Natural Language Processing in Python. *Zenodo*. https://doi.org/10.5281/zenodo.1212303
- **URL**: https://spacy.io

---

### B4. PyTorch
- **Used for**: All transformer model inference (device management, CUDA/CPU)
- **Version**: `>=2.6.0` (pinned for CVE-2025-32434 fix)
- **Citation**:
  > Paszke, A., et al. (2019). PyTorch: An Imperative Style, High-Performance Deep Learning Library. *NeurIPS 2019*. https://arxiv.org/abs/1912.01703

---

### B5. BERTopic *(Offline Topic Clustering POC — scripts/topic_clustering/ only)*
- **Used in**: Offline exploratory topic clustering script (`scripts/topic_clustering/`) — **NOT** used in the live NLP pipeline
- **Live pipeline uses**: `TopicClassifier` (Stage 9) which reuses `all-mpnet-base-v2` with zero-shot cosine similarity against 8 hand-written topic description paragraphs — no BERTopic, no additional model download
- **Paper to cite** *(only if discussing the offline POC)*:
  > Grootendorst, M. (2022). BERTopic: Neural topic modeling with a class-based TF-IDF procedure. *arXiv*. https://arxiv.org/abs/2203.05794

---

### B6. UMAP *(Topic Clustering)*
- **Used in**: BERTopic dimensionality reduction step
- **Paper to cite**:
  > McInnes, L., Healy, J., & Melville, J. (2018). UMAP: Uniform Manifold Approximation and Projection for Dimension Reduction. *arXiv*. https://arxiv.org/abs/1802.03426

---

### B7. HDBSCAN *(Topic Clustering)*
- **Used in**: BERTopic clustering step
- **Paper to cite**:
  > Campello, R. J. G. B., Moulavi, D., & Sander, J. (2013). Density-Based Clustering Based on Hierarchical Density Estimates. *PAKDD 2013*. https://doi.org/10.1007/978-3-642-37456-2_14

---

## C. Infrastructure & Web Frameworks — Acknowledgement / Citation

These are typically cited once in the Implementation/Methodology section as the infrastructure stack.

| Tool | Purpose | Citation / URL |
|------|---------|----------------|
| **FastAPI** | REST API gateway | Ramírez, S. (2018). FastAPI. https://fastapi.tiangolo.com |
| **Redis Streams** | Inter-service async messaging | Redis Ltd. (2024). Redis Streams. https://redis.io/docs/data-types/streams/ |
| **PostgreSQL + pgvector** | Persistent storage + vector search | pgvector: https://github.com/pgvector/pgvector |
| **SQLAlchemy** | ORM for PostgreSQL | SQLAlchemy (2006–2024). https://www.sqlalchemy.org |
| **Pydantic v2** | Data validation & serialisation | Colvin, S. (2023). Pydantic v2. https://docs.pydantic.dev |
| **Docker / Docker Compose** | Container orchestration | Docker Inc. (2024). https://www.docker.com |
| **Uvicorn** | ASGI server for FastAPI | Encode (2024). https://www.uvicorn.org |
| **feedparser** | RSS/Atom feed parsing | Pilgrim, M. (2004–2024). Universal Feed Parser. https://pypi.org/project/feedparser/ |
| **trafilatura** | HTML-to-text extraction | Barbaresi, A. (2021). Trafilatura: A Web Scraping Library and Command-Line Tool for Text Discovery and Extraction. *ACL 2021*. https://aclanthology.org/2021.acl-demo.15 |
| **BeautifulSoup4** | HTML parsing fallback | Richardson, L. (2007–2024). Beautiful Soup. https://www.crummy.com/software/BeautifulSoup/ |
| **Selenium + undetected-chromedriver** | JavaScript-rendered page fetching | SeleniumHQ (2024). https://www.selenium.dev |

---

## D. Datasets / Knowledge Bases — Acknowledgement

| Dataset | Used For | Citation |
|---------|---------|---------|
| **AllSides Media Bias Ratings** | Training data for `premsa/political-bias-prediction-allsides-BERT` | AllSides (2012–2024). https://www.allsides.com/media-bias/ratings |
| **CoNLL-2003** | Training data for `dslim/bert-base-NER-uncased` | Tjong Kim Sang & De Meulder (2003) — see A1 |
| **MultiNLI** | Training data for `typeform/distilbert-base-uncased-mnli` | Williams et al. (2018) — see A7 |
| **SQuAD 2.0** | Training data for `deepset/roberta-base-squad2` | Rajpurkar et al. (2018) — see A10 |
| **TweetEval** | Training data for `cardiffnlp/twitter-roberta-base-sentiment-latest` | Barbieri et al. (2020) — see A4 |

---

## E. Summary: Where to Cite in the Paper

| Paper Section | What to Cite |
|--------------|-------------|
| **3. Methodology → 3.3 NLP Pipeline** | HuggingFace Transformers (B1), spaCy (B3), PyTorch (B4), all models A1–A8 |
| **3. Methodology → 3.3.1 Preprocessing** | spaCy `en_core_web_sm` (B3) |
| **3. Methodology → 3.3.2 Centrality Scoring** | BERT-base-uncased (A8), cross-encoder NLI (A6) |
| **3. Methodology → 3.3.3 Embedding** | Sentence-BERT (B2, A2), MPNet (A2) |
| **3. Methodology → 3.3.4 Entity Recognition** | BERT-NER (A1), CoNLL-2003 (D) |
| **3. Methodology → 3.3.5 Bias Detection** | premsa BERT (A3), AllSides (D), CardiffNLP RoBERTa (A4), TweetEval (D) |
| **3. Methodology → 3.3.6 Check-Worthiness** | ClaimBuster (A5), DeBERTa (A5) |
| **3. Methodology → 3.4 Retrieval Layer** | pgvector, typeform NLI (A7), MultiNLI (D) |
| **3. Methodology → 3.2 Web Scraper** | Selenium (C), trafilatura (C), BeautifulSoup (C) |
| **3. Methodology → 3.1 Ingestor** | feedparser (C) |
| **3. Methodology → 3.5 Infrastructure** | FastAPI (C), Redis (C), PostgreSQL/pgvector (C), Docker (C) |
| **3. Methodology → 3.3.9 Topic Classification** | `sentence-transformers/all-mpnet-base-v2` (A2) — zero-shot cosine similarity, no BERTopic |
| **4. Results → 4.7 Topic Coverage (offline POC only)** | BERTopic (B5), UMAP (B6), HDBSCAN (B7) — used in `scripts/topic_clustering/` exploratory scripts only, NOT in the live NLP pipeline |

---

## F. Quick-Reference: All HuggingFace Model Cards

| Model ID | Component | HF URL |
|----------|-----------|--------|
| `dslim/bert-base-NER-uncased` | EntityRecognizer | https://huggingface.co/dslim/bert-base-NER-uncased |
| `sentence-transformers/all-mpnet-base-v2` | Embedder + TopicClassifier | https://huggingface.co/sentence-transformers/all-mpnet-base-v2 |
| `premsa/political-bias-prediction-allsides-BERT` | BiasDetector (political) | https://huggingface.co/premsa/political-bias-prediction-allsides-BERT |
| `cardiffnlp/twitter-roberta-base-sentiment-latest` | BiasDetector (sentiment) | https://huggingface.co/cardiffnlp/twitter-roberta-base-sentiment-latest |
| `whispAI/ClaimBuster-DeBERTaV2` | CheckWorthinessFilter | https://huggingface.co/whispAI/ClaimBuster-DeBERTaV2 |
| `cross-encoder/nli-distilroberta-base` | CentralityScorer / SentenceExtract | https://huggingface.co/cross-encoder/nli-distilroberta-base |
| `typeform/distilbert-base-uncased-mnli` | Retrieval NLI | https://huggingface.co/typeform/distilbert-base-uncased-mnli |
| `bert-base-uncased` | CentralityScorer | https://huggingface.co/google-bert/bert-base-uncased |
| `google/flan-t5-base` | Decontextualizer (GPU prod, CPU disabled) | https://huggingface.co/google/flan-t5-base |
| `Salesforce/mixqg-base` | Decontextualizer (GPU prod, CPU disabled) | https://huggingface.co/Salesforce/mixqg-base |
| `deepset/roberta-base-squad2` | Decontextualizer (GPU prod, CPU disabled) | https://huggingface.co/deepset/roberta-base-squad2 |
| `en_core_web_sm` | Preprocessor (spaCy) | https://spacy.io/models/en#en_core_web_sm |
