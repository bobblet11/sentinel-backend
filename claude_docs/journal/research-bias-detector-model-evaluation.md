---
## [2026-04-12] BiasDetector Model Evaluation & Fix Plan

**Agent**: `research-and-plan`
**Branch**: `newretrieval-fixes`
**Triggered By**: User audit identifying 5 bugs in BiasDetector + request to evaluate model alternatives.

### Summary
Researched political bias detection models to replace the current zero-shot NLI approach (`typeform/distilbert-base-uncased-mnli`, ~76% acc). Evaluated 7 candidates across accuracy, model size, CPU viability, license, and task alignment. Produced a ranked recommendation and a 6-step implementation plan covering all 5 identified bugs plus the model upgrade.

### Files Created
| File Path | Type | Description |
|-----------|------|-------------|
| `claude_docs/research-and-plan/bias-detector-model-evaluation-2026-04-12.md` | Research | Model comparison table, candidate evaluations, ranked recommendations |
| `claude_docs/nlp/bias-detector-fix-plan.md` | Plan | 6-step implementation plan with dependency graph, verification checklist, risk summary |

### Key Decisions
1. **Political bias model**: Switch to `premsa/political-bias-prediction-allsides-BERT` (F1=0.904, 3-class Left/Center/Right, trained on AllSides news data)
2. **Sentiment model**: Keep `cardiffnlp/twitter-roberta-base-sentiment-latest` (works well, not worth risk of change)
3. **Architecture**: Keep two-model approach (no single model does both political lean + sentiment)

### Rejected Alternatives
- `facebook/bart-large-mnli`: Better zero-shot but 1.6GB, still indirect approach
- `mediabiasgroup/magpie-babe-ft`: Detects linguistic bias not political lean, 1.1GB
- `d4data/bias-detection-model`: Binary only (biased/unbiased), no published metrics
- `bucketresearch/politicalBiasBERT`: Same task but no published metrics, stale

### Pipeline Impact
No changes made to code yet. Plan targets 6 files: `bias.py`, `test_components.py`, `config.py`, `claimextract.py`, `manager.py`, `redis_models.py`. No stream interface or schema changes. BiasProfile output format unchanged.
