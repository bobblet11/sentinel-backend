# Merge Resolution Plan: refactor/nlp <- newretrieval-fixes

**Date**: 2026-03-31
**Branch**: `refactor/nlp` (yours) merging `origin/newretrieval-fixes` (teammates)
**Rule**: Retrieval/scraper changes from `newretrieval-fixes` are the new standard. NLP code adapts to them.

---

## Question 1: `.env.template` -- Which NLP Model Variables Are Actually Used?

### Finding: `NLP_QG_MODEL`, `NLP_QA_MODEL`, `NLP_GEN_MODEL` ARE actively consumed

`refactor/nlp` config.py (lines 107-109) reads all three via `get_env_var()` with hardcoded defaults:

```python
QG_MODEL = get_env_var("NLP_QG_MODEL", str, config_logger, QG_MODEL)    # default: "Salesforce/mixqg-base"

QA_MODEL = get_env_var("NLP_QA_MODEL", str, config_logger, QA_MODEL)    # default: "deepset/roberta-base-squad2"
GEN_MODEL = get_env_var("NLP_GEN_MODEL", str, config_logger, GEN_MODEL) # default: "google/flan-t5-base"
```

These are used by the new `ClaimExtraction` pipeline (decontextualization stage). They are NOT dead variables.

Meanwhile, `newretrieval-fixes` config.py does NOT reference these variables at all -- it uses the old pipeline architecture (Preprocessor, CentralityScorer, Embedder, BiasDetector, EntityRecognizer, CheckWorthinessFilter) which has no decontextualization step.

### What `newretrieval-fixes` teammates are missing

Their `.env.template` deprecated `USE_GPU` and `NLP_BASE`, but these are still needed:
- `USE_GPU` is consumed by both branches' config.py and is passed as an environment variable in both CPU and GPU docker-compose service definitions
- `NLP_BASE` is NOT consumed by code (it was used for `build.args.BASE_IMAGE` but the docker-compose hardcodes the image names directly) -- it truly is dead

### Resolution: Correct final `.env.template`

**Keep from `refactor/nlp`:**
- `NLP_QG_MODEL=Salesforce/mixqg-base` -- actively consumed
- `NLP_QA_MODEL=deepset/roberta-base-squad2` -- actively consumed
- `NLP_GEN_MODEL=google/flan-t5-base` -- actively consumed
- `USE_GPU=false` -- actively consumed by config.py line 112

**Remove:**
- `NLP_BASE=sentinel/python-ml-cpu:3.12` -- dead variable, never read by any code. The docker-compose hardcodes `BASE_IMAGE` directly.

**Note for teammates:** When they pull the merged branch, they need to add `NLP_QG_MODEL`, `NLP_QA_MODEL`, and `NLP_GEN_MODEL` to their local `.env` files. However, since `config.py` provides hardcoded defaults for all three, the service will work without them -- the env vars are optional overrides. This means no urgent action is needed on their side.

### Additional model variable differences between branches

The two branches have diverged significantly on which models are used:

| Variable | `refactor/nlp` value | `newretrieval-fixes` value |
|---|---|---|
| `NLP_EMBEDDING_MODEL` | `sentence-transformers/all-mpnet-base-v2` | `all-MiniLM-L6-v2` |
| `NLP_NER_MODEL` | `flair/ner-english-large` | `dslim/bert-base-NER` |
| `NLP_BIAS_MODEL` | `unitary/toxic-bert` (maps to `typeform/distilbert-base-uncased-mnli` internally) | `facebook/bart-large-mnli` |

Since you own the NLP layer, **your model choices are correct**. The `.env.template` should use your values. The `newretrieval-fixes` values are outdated for the new pipeline.

---

## Question 2: Docker Network Strategy -- `external: true` is Correct

### Finding: Both branches already agree

Surprising finding: The merge analysis was based on an earlier state. **Both branches now use `external: true`** for `sentinel-net`. The current `refactor/nlp` branch's `docker-compose.yml` (line 388-390) already reads:

```yaml
networks:
  sentinel-net:
    external: true
```

And `newretrieval-fixes` has the identical block.

### `deploy.sh` handles creation

The current branch's `deploy.sh` (line 202) creates the network before `docker-compose up`:

```bash
sudo docker network create --driver bridge sentinel-net 2>/dev/null || true
```

The `newretrieval-fixes` `deploy.sh` does NOT have this line -- it expects the network to already exist.

### Resolution

**Keep `refactor/nlp`'s `deploy.sh`** which has the `docker network create` call. This is a safety net: it creates the network if it does not exist, and silently succeeds if it does. The `external: true` in docker-compose is correct for both branches.

The `hf-model-cache` named volume mentioned in the original merge analysis does NOT exist on either branch -- this was a false alarm.

### Actual docker-compose.yml differences

The real diff between the two branches is minimal and non-conflicting:
1. Postgres port binding: `refactor/nlp` uses `${POSTGRES_EXTERNAL_PORT:-${POSTGRES_PORT:-5432}}:5432` (more flexible) vs `${POSTGRES_PORT}:5432`
2. Trailing whitespace fixes in `build:` keys
3. GPU service: `refactor/nlp` replaces deprecated `gpus: all` with proper `deploy.resources.reservations.devices` block

All of these are improvements from `refactor/nlp` that should be kept.

---

## Question 3: Preprocessor Merge Strategy

### Detailed comparison

**What `newretrieval-fixes` has that `refactor/nlp` does NOT:**
1. `junk_pattern` -- catches encoded/debug fragments like `in/[a-z0-9/_-]{6,}`, broken telemetry tails, video player artifacts
2. `reuters_meta_pattern` -- catches Reuters-specific metadata lines (reporting bylines, licensing rights, Thomson Reuters boilerplate)
3. `seen_lines` duplicate detection -- deduplicates exact lines (common in scraped nav blocks)
4. Whitespace normalization per line: `re.sub(r'\s+', ' ', line)`
5. Single-word section menu filtering: drops lines like "Summary", "Companies", "Latest" and short taxonomy labels like "Business", "Economics"
6. Extended `footer_cutoff_pattern` with Reuters/Guardian/Middle East-specific footers

**What `refactor/nlp` has that `newretrieval-fixes` does NOT:**
1. `_photo_credit_re` compiled at `__init__` -- comprehensive photo agency regex (Getty, Reuters, AFP, NTB, EPA, Shutterstock, Alamy, Corbis, etc.)
2. Line-level photo credit guard with verb check -- drops `/`-separated agency attributions but preserves sentences that mention agencies in context ("Reuters reported that...")
3. Sentence-level photo credit guard in `run()` -- catches credits not separated by newlines
4. Config-driven constants (`PREPROCESS_MIN_TOKENS`, `PHOTO_CREDIT_MAX_LEN`) imported from `config.py`
5. Accepts injected spaCy model via `__init__(nlp=None)` for shared model reuse
6. Inherits from `SentenceProcessor` (new base class) instead of `NLPComponent`
7. Returns `List[SentenceScore]` from `run()` instead of mutating `result.sentences` directly
8. Extended `ui_pattern` with Guardian-specific patterns ("support the guardian", "remind me in", etc.)

### Resolution: `refactor/nlp` is the base, cherry-pick features from `newretrieval-fixes`

The `refactor/nlp` preprocessor is architecturally correct for the new pipeline (returns list, uses `SentenceProcessor` base, config-driven). Use it as the base and merge in the following from `newretrieval-fixes`:

1. **Add `junk_pattern`** -- paste it after `byline_pattern` in `_clean_and_repair_structure()`
2. **Add `reuters_meta_pattern`** -- paste it after `junk_pattern`
3. **Add `seen_lines` dedup** -- add `seen_lines = set()` after `cleaned_lines = []`, and add the dedup check in the loop
4. **Add whitespace normalization** -- add `line = re.sub(r'\s+', ' ', line)` after `line = line.strip()`
5. **Add section menu/taxonomy filtering** -- add the single-word label check and the `line.lower() in {...}` check
6. **Extend `footer_cutoff_pattern`** -- merge the additional patterns from `newretrieval-fixes` (Reuters trust principles, Guardian donations, suggested topics, etc.)

Do NOT take:
- The `NLPComponent` base class (use `SentenceProcessor`)
- The `result.sentences = sentence_objects` mutation pattern (use `return sentence_objects`)
- The missing config imports

---

## Step-by-Step: Resolving Each Conflicted File

### File 1: `.gitignore`

**Action**: Take both additions. Combine the union of both branches.

Final `.gitignore` should include everything from the current branch plus `*.zip`, `.zip`, `backups.zip` from `newretrieval-fixes`. The current branch already has `backups` in `.gitignore`, so the zip patterns are additive.

```
# Keep everything currently in refactor/nlp's .gitignore (lines 1-27)
# Add from newretrieval-fixes:
*.zip
.zip
backups.zip
```

Note: `node_modules/`, `package-lock.json`, `package.json` are showing as untracked in git status -- consider adding `node_modules/` to `.gitignore` as well.

### File 2: `configs/.env.template`

**Action**: Start from `newretrieval-fixes` base (since retrieval/scraper vars are their standard), then re-add the NLP variables that your code needs.

Specifically, the NLP section should be:

```ini
# NLP Service
NLP_INPUT_STREAMS=user:to.be.nlp,background:to.be.nlp
NLP_USER_OUTPUT_STREAM=user:to.be.retrieval
NLP_BACKGROUND_OUTPUT_STREAM=background:to.be.retrieval
NLP_FAILURE_OUTPUT_STREAM=failure:to.be.nlp
NLP_GROUP_NAME=default
NLP_CONSUMER_NAME=nlp-1
NLP_BATCH_SIZE=10
NLP_MAX_WORKERS=2
NLP_EMBEDDING_MODEL=sentence-transformers/all-mpnet-base-v2
NLP_NER_MODEL=flair/ner-english-large
NLP_BIAS_MODEL=unitary/toxic-bert
NLP_QG_MODEL=Salesforce/mixqg-base
NLP_QA_MODEL=deepset/roberta-base-squad2
NLP_GEN_MODEL=google/flan-t5-base
USE_GPU=false
# USE_GPU=true

NLP_SHM_SIZE=4gb
NLP_CPU_LIMIT=1.0
NLP_MEMORY_LIMIT=6G
NLP_CPU_RESERVATION=0.5
NLP_MEMORY_RESERVATION=2G
```

Key decisions:
- `NLP_EMBEDDING_MODEL`: use `sentence-transformers/all-mpnet-base-v2` (your value, matches config.py default)
- `NLP_NER_MODEL`: use `flair/ner-english-large` (your value, but note config.py default is `dslim/bert-base-NER-uncased` -- the env var overrides it, which is intentional)
- Remove `NLP_BASE` (dead variable)
- Keep `USE_GPU=false` uncommented (actively consumed)
- Use `NLP_MEMORY_LIMIT=6G` (your value, needed for the larger model set)
- Use `COMPOSE_PROFILES=api,ingestor,scraper,nlp-cpu` (your value, with explicit `-cpu` suffix matching docker-compose profile names)

### File 3: `docker/compose/docker-compose.yml`

**Action**: Keep `refactor/nlp`'s version as the base. The differences are small and all favor the current branch.

During merge, accept the current branch's changes:
- Postgres port: keep the more flexible `${POSTGRES_EXTERNAL_PORT:-${POSTGRES_PORT:-5432}}:5432`
- `build:` whitespace fixes: keep (cosmetic but cleaner)
- GPU service: keep `deploy.resources.reservations.devices` block, remove deprecated `gpus: all`
- Network: both are `external: true` -- no conflict

The only thing to add from `newretrieval-fixes` is: nothing. The compose files are functionally identical where it matters, and `refactor/nlp` has strictly better GPU device configuration.

However, you need to **add the new env vars to the NLP service environment blocks**. Currently, neither branch's docker-compose passes `NLP_QG_MODEL`, `NLP_QA_MODEL`, or `NLP_GEN_MODEL` to the container. Since `config.py` reads them with defaults, they will work without explicit passthrough -- but for completeness and overridability, consider adding to both `nlp-service-cpu` and `nlp-service-gpu`:

```yaml
      - NLP_QG_MODEL=${NLP_QG_MODEL:-Salesforce/mixqg-base}
      - NLP_QA_MODEL=${NLP_QA_MODEL:-deepset/roberta-base-squad2}
      - NLP_GEN_MODEL=${NLP_GEN_MODEL:-google/flan-t5-base}
```

This is optional -- the env vars will be picked up from the `.env` file via `x-common-env` / `env_file`. But explicit is better than implicit for model configuration.

### File 4: `microservices/nlp/components/preprocess.py`

**Action**: Keep `refactor/nlp`'s version as the base (it has the correct architecture). Cherry-pick the 6 features listed in Question 3 above.

Concrete steps:
1. Keep the `SentenceProcessor` base class, `__init__` with optional `nlp` param, `_photo_credit_re`, config imports
2. In `_clean_and_repair_structure()`:
   a. After `cleaned_lines = []`, add `seen_lines = set()`
   b. Extend `footer_cutoff_pattern` with the additional patterns from `newretrieval-fixes` (Reuters, Guardian, suggested topics, etc.)
   c. Add `junk_pattern` after `byline_pattern`
   d. Add `reuters_meta_pattern` after `junk_pattern`
   e. After `line = line.strip()`, add `line = re.sub(r'\s+', ' ', line)`
   f. After the `len(line) < 4` check, add duplicate detection:
      ```python
      lowered = line.lower()
      if lowered in seen_lines:
          continue
      seen_lines.add(lowered)
      ```
   g. In PHASE 3 filtering, add `if junk_pattern.search(line): continue` and `if reuters_meta_pattern.search(line): continue`
   h. Add the single-word/taxonomy filtering:
      ```python
      if line.lower() in {"summary", "companies", "latest", "archive", "browse", "videos", "pictures", "graphics", "podcasts", "authors", "home"}:
          continue
      if re.fullmatch(r"[A-Za-z& ]{3,30}", line):
          token_count = len(line.split())
          if token_count <= 3:
              continue
      ```
3. Keep the `run()` method exactly as-is (returns `List[SentenceScore]`, has sentence-level photo credit guard)

### File 5: `microservices/nlp/nlp_service.py`

**Action**: Keep `refactor/nlp`'s version. Add GPU detection logging from `newretrieval-fixes`.

In the `__init__` method, before `self.options = options or NLPOptions()`, add:

```python
if torch.cuda.is_available():
    self.logger.info("GPU DETECTED")
else:
    self.logger.info("GPU NOT DETECTED")
```

Everything else stays as `refactor/nlp` has it: `ClaimExtraction` pipeline, `ModelManager`, typed dispatch, CUDA OOM handling, etc.

---

## Merge Execution Commands

```bash
# 1. Start the merge (from refactor/nlp branch)
git merge origin/newretrieval-fixes

# 2. Resolve each file (in any order)
# Edit each conflicted file per the instructions above

# 3. Stage resolved files
git add .gitignore
git add configs/.env.template
git add docker/compose/docker-compose.yml
git add microservices/nlp/components/preprocess.py
git add microservices/nlp/nlp_service.py

# 4. Complete the merge
git commit -m "merge: integrate newretrieval-fixes into refactor/nlp

Resolves 5 conflicts:
- .gitignore: combined both branches' ignore patterns
- .env.template: kept NLP model vars (actively consumed), removed dead NLP_BASE
- docker-compose.yml: kept external network, proper GPU device config
- preprocess.py: kept refactor/nlp architecture, added newretrieval-fixes'
  junk/Reuters/dedup/taxonomy filters
- nlp_service.py: kept ClaimExtraction pipeline, added GPU detection logging"

# 5. Validate
python -c "from microservices.nlp.config import QG_MODEL, QA_MODEL, GEN_MODEL; print('Config OK')"
python -c "from microservices.nlp.components.preprocess import Preprocessor; print('Preprocessor OK')"
python -c "from microservices.nlp.nlp_service import NLPService; print('Service OK')"
```

---

## Post-Merge Verification Checklist

- [ ] All 5 conflict files resolved and staged
- [ ] `python -c "import microservices.nlp.config"` succeeds
- [ ] `python -c "from microservices.nlp.components.preprocess import Preprocessor"` succeeds
- [ ] `python -c "from microservices.nlp.nlp_service import NLPService"` succeeds
- [ ] `./scripts/format_and_lint.sh` passes (or only pre-existing warnings)
- [ ] `pytest tests/` -- no new failures
- [ ] Verify scraper output schema matches what NLP pipeline expects (stream message shapes)
- [ ] Verify NLPResult schema matches what retrieval layer expects
