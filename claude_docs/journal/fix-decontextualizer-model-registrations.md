---
date: 2026-04-06
agent: claude-inline
branch: newretrieval-fixes
files_changed:
  - common/model_manager/manager.py
---

## What changed

Added 4 missing `ModelEntry` registrations to `register_defaults()` in `common/model_manager/manager.py`, inside the `if enable_decontextualization:` block:

- `DECONTEXT_QG_MODEL` — `Salesforce/mixqg-base`, loader: `auto_model_seq2seq`, ~900MB
- `DECONTEXT_QG_TOKENIZER` — `Salesforce/mixqg-base`, loader: `auto_tokenizer`, ~10MB
- `DECONTEXT_QA_MODEL` — `deepset/roberta-base-squad2`, loader: `auto_model_qa`, ~500MB
- `DECONTEXT_QA_TOKENIZER` — `deepset/roberta-base-squad2`, loader: `auto_tokenizer`, ~10MB

Model names read from env vars `NLP_QG_MODEL` and `NLP_QA_MODEL` with hardcoded defaults.

## Why

The NLP service was crash-looping on startup with `ModelNotFoundError: Model key 'DECONTEXT_QG_MODEL' is not registered`. The `Decontextualizer` component (`components/decontext.py`) expects 6 model keys from the ModelManager but only 2 (`DECONTEXT_MODEL`, `DECONTEXT_TOKENIZER`) were ever registered. The 4 QG/QA model registrations were simply missing.

## Memory budget

Adding these 4 models adds ~1420MB. Total estimated NLP model memory is ~4360MB, within the configured `NLP_MEMORY_LIMIT=6G`.

## Rollback

Set `ENABLE_DECONTEXTUALIZATION=false` in the env to skip all decontext model registration.
