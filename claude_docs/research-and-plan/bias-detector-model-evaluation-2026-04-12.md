# BiasDetector Model Evaluation & Bug Fix Research

**Date:** 2026-04-12
**Component:** `microservices/nlp/components/bias.py` (BiasDetector)
**Confidence Level:** High

---

## 1. Problem Statement

The BiasDetector component is non-operational due to 5 identified bugs, and the current model choice (`typeform/distilbert-base-uncased-mnli` for zero-shot political bias classification) is suboptimal. This research evaluates alternative models and informs the fix plan.

---

## 2. Current Implementation

| Aspect | Current Choice |
|---|---|
| Political bias model | `typeform/distilbert-base-uncased-mnli` (zero-shot NLI) |
| Sentiment model | `cardiffnlp/twitter-roberta-base-sentiment-latest` |
| Approach | Two-model pipeline: zero-shot NLI for political lean + dedicated sentiment model for tone |
| Labels (political) | `["left-leaning", "centrist", "right-leaning"]` via hypothesis template |
| Labels (sentiment) | `negative`, `neutral`, `positive` |
| Model size (combined) | ~760 MB (260 + 500 MB estimated) |

---

## 3. Research: Political Bias Model Candidates

### 3.1 Candidate Comparison Table

| Model | Architecture | Task | Labels | Size (MB) | Trained On | F1 / Accuracy | CPU Speed | License | Maintained |
|---|---|---|---|---|---|---|---|---|---|
| **typeform/distilbert-base-uncased-mnli** (current) | DistilBERT-base | Zero-shot NLI | Any (user-defined) | ~260 | MNLI (433k pairs) | 82% MNLI acc; ~76% zero-shot | Fast (~0.3s) | Apache-2.0 | Stale (no updates since 2021) |
| **d4data/bias-detection-model** | DistilBERT-base | Binary classification | Biased / Non-Biased | ~268 | MBAD news dataset | Not published (est. ~80-85% F1) | Fast (~0.3s) | Apache-2.0 | Low (last update 2023) |
| **bucketresearch/politicalBiasBERT** | BERT-base | 3-class classification | Left / Center / Right | ~440 | Political texts | Not published | Medium (~0.5s) | Apache-2.0 | Low (last update Jul 2023) |
| **premsa/political-bias-prediction-allsides-BERT** | BERT-base | 3-class classification | Left / Center / Right | ~440 | AllSides dataset | **F1 = 0.904** | Medium (~0.5s) | Apache-2.0 | Active (2024-2025) |
| **premsa/political-bias-prediction-allsides-mDeBERTa** | mDeBERTa | 3-class classification | Left / Center / Right | ~560 | AllSides dataset | **F1 = 0.918** | Slower (~0.8s) | Apache-2.0 | Active (2024-2025) |
| **mediabiasgroup/magpie-babe-ft** | XLM-RoBERTa (0.3B) | Binary (biased/unbiased) | Biased / Non-Biased | ~1100 | 59 bias tasks (LBM) + BABE | 3.3% F1 improvement over prior SOTA | Slow (~1.5s) | Research | Active (2025) |
| **facebook/bart-large-mnli** | BART-Large | Zero-shot NLI | Any (user-defined) | ~1600 | MNLI | 88.2% acc; much better zero-shot | Slow (~1.2s) | MIT | Maintained |

### 3.2 Analysis

**Why the current model is a poor choice:**
- `typeform/distilbert-base-uncased-mnli` was trained on MNLI, a generic NLI dataset -- it has *zero* political bias training data.
- HuggingFace forum users report "very poor results" for zero-shot with this model vs. BART-large-MNLI.
- Zero-shot NLI for political bias is an indirect approach -- the model has never seen political content during training and relies entirely on surface-level entailment heuristics.
- Reported zero-shot accuracy ~76% on general tasks, likely worse on nuanced political classification.

**Why a fine-tuned political bias model is better:**
- `premsa/political-bias-prediction-allsides-BERT` achieves F1=0.904 on a 3-class Left/Center/Right task using AllSides labeled data -- news articles rated by editorial teams.
- The labels (Left/Center/Right) map directly to BiasProfile's existing `bias_category` field.
- BERT-base size (~440MB) is actually smaller than the combined current two-model load.
- Direct classification (single forward pass) vs. zero-shot NLI (requires hypothesis template construction) is simpler and faster.

**Why MAGPIE and mDeBERTa are not recommended:**
- MAGPIE (`magpie-babe-ft`) is 1.1GB and detects *linguistic bias* (biased vs unbiased language) not political lean -- different task.
- mDeBERTa variant achieves F1=0.918 but is larger (~560MB) and uses a different architecture that adds complexity. The BERT variant at F1=0.904 is a better tradeoff for this project.

**Why d4data is not recommended:**
- Binary classification (biased/unbiased) does not provide Left/Center/Right classification.
- No published evaluation metrics.

### 3.3 Recommendation: Political Bias Model

**Top choice: `premsa/political-bias-prediction-allsides-BERT`**

Justification:
1. F1=0.904 on Left/Center/Right classification -- directly maps to existing BiasProfile schema
2. BERT-base architecture (~440MB) is well-supported on CPU and GPU
3. Direct classification eliminates the fragile zero-shot hypothesis template approach
4. Trained on AllSides news data -- domain-matched to the Sentinel use case
5. Apache-2.0 license, maintained through 2024-2025
6. Replaces `zero-shot-classification` pipeline with simpler `text-classification` pipeline

**Risk:** Model outputs classes as `[0]=Left, [1]=Center, [2]=Right` -- need to map label IDs to strings. This is straightforward in the BiasDetector code.

---

## 4. Research: Sentiment Model

### 4.1 Assessment of Current Model

`cardiffnlp/twitter-roberta-base-sentiment-latest` is:
- Well-established (trained on 124M tweets)
- RoBERTa-base (~500MB) -- the largest single model in the bias pipeline
- Actively maintained by CardiffNLP
- Outputs negative/neutral/positive with confidence scores

### 4.2 Lighter Alternatives

| Model | Size | Architecture | Notes |
|---|---|---|---|
| DistilBERT sentiment variants | ~260MB | DistilBERT | 40% smaller, ~95% of BERT performance |
| `lxyuan/distilbert-base-multilingual-cased-sentiments-student` | ~260MB | DistilBERT | Knowledge-distilled from teacher model |

### 4.3 Recommendation: Sentiment Model

**Keep the current model (`cardiffnlp/twitter-roberta-base-sentiment-latest`).**

Justification:
1. It works well and is production-proven
2. The potential savings (~240MB) are modest relative to the risk of regression
3. Sentiment is a secondary signal in BiasProfile -- not worth optimizing aggressively
4. The bug fixes are the higher priority; model swaps add risk

---

## 5. Single Model vs Two-Model Approach

**Keep the two-model approach.**

Justification:
1. No single model exists that does both political lean classification AND sentiment analysis in one forward pass
2. The tasks are fundamentally different (political lean is about ideological framing; sentiment is about emotional valence)
3. Keeping them separate allows independent model upgrades
4. With the political model change, total memory is ~440 + 500 = 940MB (vs current 260 + 500 = 760MB), a modest increase offset by much better accuracy

---

## 6. Summary of Recommendations

| Decision | Recommendation | Confidence |
|---|---|---|
| Political bias model | Switch to `premsa/political-bias-prediction-allsides-BERT` | High |
| Sentiment model | Keep `cardiffnlp/twitter-roberta-base-sentiment-latest` | High |
| Architecture | Keep two-model approach | High |
| Bug 1 fix (NameError) | Move `result` creation before try block | High |
| Bug 2 fix (wrong key) | Change `"BIAS"` to `["BIAS_POLITICAL", "BIAS_SENTIMENT"]` | High |
| Bug 3 fix (test harness) | Pass `device_config` and `model_manager` to `BiasDetector()`, use `StreamMessage` | High |
| Bug 4 fix (lazy write) | Low priority but should use unconditional write for bias_profile | Medium |
| Bug 5 fix (unconditional load) | Lazy-init or conditional instantiation | High |
