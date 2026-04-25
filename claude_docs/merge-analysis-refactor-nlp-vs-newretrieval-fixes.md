# Merge Analysis: refactor/nlp vs newretrieval-fixes

**Date**: 2026-03-31
**Current Branch**: `refactor/nlp`
**Target Branch**: `origin/newretrieval-fixes`
**Merge Base**: `0994754f3818cdcb1c4822438ddd257cf309a3af`

---

## Summary

The branches **are NOT merge-friendly**. A merge would encounter **5 conflicted files** that require manual resolution. The conflicts are **structural and architectural** — the two branches are taking fundamentally different approaches to refactoring and fixing the pipeline.

- **refactor/nlp**: Comprehensive NLP pipeline rewrite using ModelManager, new component architecture, removal of old test files
- **newretrieval-fixes**: Focused retrieval layer fixes, parser improvements, scraper enhancements, without touching core NLP structure

This is a **high-risk merge** due to divergent NLP pipelines and incompatible architectural changes.

---

## Conflicted Files (5 total)

### 1. `.gitignore`

**Type**: Addition conflict — both branches add ignore patterns

**HEAD (refactor/nlp) adds**:
```
.cache
CLAUDE.md
.claude
claude_docs
.github
GEMINI.md
```

**newretrieval-fixes adds**:
```
*.zip
.zip
backups.zip
```

**Assessment**: These are non-overlapping; **can be resolved by taking both additions**. No semantic conflict.

**Resolution Strategy**: Combine both ignore lists into one clean `.gitignore` section.

---

### 2. `configs/.env.template`

**Type**: Content conflict — both branches modify NLP environment variables

**HEAD (refactor/nlp) changes** (lines 87–92):
- Adds new NLP model configuration variables:
  - `NLP_QG_MODEL=Salesforce/mixqg-base` (question generation)
  - `NLP_QA_MODEL=deepset/roberta-base-squad2` (QA)
  - `NLP_GEN_MODEL=google/flan-t5-base` (generation)
  - `USE_GPU=false`
  - `NLP_BASE=sentinel/python-ml-cpu:3.12`

**newretrieval-fixes changes** (lines 87–96):
- Removes the new model variables
- Marks them as deprecated with comment: "these env variables are deprecated, use the profiles instead"
- Keeps the commented-out `USE_GPU` and `NLP_BASE` examples

**Assessment**: **Direct content conflict**. The branches have **opposite intent**:
- `refactor/nlp` is **adding** new model config variables
- `newretrieval-fixes` is **removing** them and marking them deprecated

**Architectural Impact**: This signals a schema mismatch. If `refactor/nlp` expects these variables at runtime and they're not in `.env`, the NLP service will fail or fall back to defaults.

**Resolution Strategy**:
- Understand which approach is correct for the current codebase
- If `refactor/nlp` newly uses `NLP_QG_MODEL`, `NLP_QA_MODEL`, `NLP_GEN_MODEL`, you **must keep them** and update `newretrieval-fixes` approach
- If they're truly deprecated, strip them from `refactor/nlp` first

**Critical Question**: Does `microservices/nlp/config.py` (heavily modified in both branches) reference these variables?

---

### 3. `docker/compose/docker-compose.yml`

**Type**: Structural conflict — both branches modify service definitions and network setup

**HEAD (refactor/nlp) changes** (lines 388–392):
```yaml
networks:
  sentinel-net:
    driver: bridge

volumes:
  hf-model-cache:
```
- Adds a **new named volume** `hf-model-cache` for HuggingFace model caching
- Sets network driver explicitly as `bridge`

**newretrieval-fixes changes** (lines 388–395):
```yaml
networks:
  sentinel-net:
    external: true
```
- Marks the network as **external** (expected to be created beforehand)
- Does NOT define a volume for HuggingFace cache

**Assessment**: **Critical architectural conflict**.

- `refactor/nlp` expects Docker to **create** the network and cache volume on compose up
- `newretrieval-fixes` expects the network to **already exist** externally (manual setup required)

This will cause **deployment failure** if merged naively. The compose file will try to use an external network that may not exist.

**Additional Context**: The rest of `docker-compose.yml` is heavily modified in both branches (67 lines changed in newretrieval-fixes, 5 lines in refactor/nlp), but most changes are compatible (service definitions, environment variables). The **only hard conflict** is the network and volume setup at the end.

**Resolution Strategy**:
- Understand your deployment strategy: do you pre-create `sentinel-net` externally, or should compose create it?
- If external network is required, remove `hf-model-cache` volume definition from refactor/nlp and update any NLP service mounts that depend on it
- If compose should create the network, keep refactor/nlp's `driver: bridge` approach but ensure all services mount the volume correctly

**Critical Question**: Do any NLP or retrieval services mount `hf-model-cache` in their volumes? Check the full compose file.

---

### 4. `microservices/nlp/components/preprocess.py`

**Type**: Complex merge conflict — both branches heavily rewrite the preprocessor

**HEAD (refactor/nlp)** (~250 lines):
- Rewrites the entire `_clean_and_repair_structure()` method with a **unified single-pass approach**
- Applies filters in a specific order (footer cutoff → UI → time meta → credits → bylines → photo credits → structural repair)
- Uses local regex patterns (`photo_credit_pattern`, `footer_cutoff_pattern`, etc.)
- Adds **sentence-level photo credit guard** (lines 257–264)
- Preserves old logic for byline and photo credit detection

**newretrieval-fixes** (~200 lines):
- Also rewrites `_clean_and_repair_structure()` but with a **different filtering strategy**
- Adds **new junk pattern matching** (lines 107–113):
  ```regex
  in/[a-z0-9/_-]{6,}|
  more data|summary reportdiagnosisdensity|
  \d{1,4}\s+\d{1,4}\s+n/?a|
  ```
- Adds **Reuters-specific metadata pattern** (lines 140–152)
- Adds **section menu/taxonomy filtering** (lines 213–216)
- Uses a **multi-phase approach** with explicit comments: PHASE 2 (cutoff), PHASE 3 (regex filtering), PHASE 4 (structural repair)
- Adds **duplicate line detection** using a `seen_lines` set (lines 165–168)
- Uses regex normalization: `re.sub(r'\s+', ' ', line)` (line 156)

**Assessment**: **Both approaches are valid but incompatible**. They solve overlapping problems (article cleaning) with different strategies.

- **refactor/nlp**: Simpler, more direct; lacks junk/Reuters metadata handling
- **newretrieval-fixes**: More comprehensive for Reuters articles; more robust against edge cases

**Merged conflicts** (5 separate conflict blocks in the file):
1. Line 104–106: Photo credit pattern definition
2. Line 123–138: Photo credit filtering logic
3. Line 183–199: Structural repair section
4. Line 199–207: Phase 2–3 comments (refactor/nlp has inline logic, newretrieval-fixes has explicit phases)
5. Line 219–221: Structural repair comment and implementation

**Resolution Strategy**:
- **Do NOT naively accept one side**. The two approaches solve different problems.
- Merge the logic by taking:
  1. The **multi-phase structure** from newretrieval-fixes (cleaner organization)
  2. The **junk and Reuters patterns** from newretrieval-fixes (handles real-world articles better)
  3. The **sentence-level photo credit guard** from refactor/nlp if not already in newretrieval-fixes
  4. The **duplicate line detection** from newretrieval-fixes
- Test the result thoroughly on sample articles from BBC, Reuters, and other outlets

**Critical Question**: Are there new patterns in `refactor/nlp`'s photo credit detection that newretrieval-fixes lacks? (Probably not, but verify.)

---

### 5. `microservices/nlp/nlp_service.py`

**Type**: Content conflict — both branches modify NLP service initialization

**HEAD (refactor/nlp)** (lines 86–98):
```python
self.options = options or NLPOptions()

```
(Simple assignment, no GPU logging)

**newretrieval-fixes** (lines 91–95):
```python
if torch.cuda.is_available():
    self.logger.info("GPU DETECTED")
else:
    self.logger.info("GPU NOT DETECTED")
self.options = options or NLPOptions()
```
(Adds explicit GPU availability logging before options assignment)

**Assessment**: **Trivial content conflict**. Both branches set `self.options`, but newretrieval-fixes adds GPU detection logging that refactor/nlp removed.

**Resolution Strategy**: **Take both**. The GPU logging is valuable for debugging. The merged version should be:
```python
if torch.cuda.is_available():
    self.logger.info("GPU DETECTED")
else:
    self.logger.info("GPU NOT DETECTED")
self.options = options or NLPOptions()
```

**Note**: This is a **secondary conflict** compared to the broader NLP architecture changes. refactor/nlp heavily rewrites the NLP pipeline (ModelManager, new components), while newretrieval-fixes only touches this small init block. The real risk is that refactor/nlp's new pipeline components may not work with newretrieval-fixes' unchanged NLP models and configuration.

---

## Broader Architectural Concerns

### 1. **NLP Pipeline Architecture Divergence** (HIGH RISK)

- **refactor/nlp**: Introduces `ModelManager` (from `common/model_manager/`) to centralize model loading and lifecycle. Restructures components to use a flat pipeline with typed dispatch (SentenceGenerator, SentenceProcessor, SentenceConsumer, ArticleProcessor). Removes old components (centrality.py, dedupe.py, registry.py) and adds new ones (claimextract.py, sentenceextract.py, device.py).

- **newretrieval-fixes**: Does NOT touch the NLP component architecture. Only adds parsing improvements to the scraper and retrieval layer fixes. Keeps the original NLP pipeline intact.

**Impact**: If you merge these branches, you will have:
- refactor/nlp's new ModelManager and ClaimExtraction-based pipeline
- newretrieval-fixes' updated scraper parsers (BBC, CBS, Guardian, etc.)
- Potential mismatch if refactor/nlp's new components expect different inputs from the scraper than newretrieval-fixes provides

**Mitigation**: After merging, you MUST:
1. Run the full E2E pipeline (scrape → NLP → retrieval) with test articles
2. Verify that scraper output matches what the new NLP pipeline expects
3. Check all stream message schemas haven't drifted

### 2. **Retrieval Layer Touch Points** (MEDIUM RISK)

- **refactor/nlp**: Only touches NLP; does NOT modify retrieval layer. Changes to `common/models/api/redis_models.py` are small (9 lines).

- **newretrieval-fixes**: Extensively modifies retrieval layer (`microservices/retrieval_layer/`) and updates stream handling in the scraper.

**Impact**: The two branches should be mostly compatible here, but verify that the NLPResult schema changes in refactor/nlp are compatible with how newretrieval-fixes' retrieval layer consumes them.

### 3. **Docker and Deployment Divergence** (MEDIUM RISK)

- **refactor/nlp**: Adds `NLP_BASE`, `NLP_QG_MODEL`, `NLP_QA_MODEL`, `NLP_GEN_MODEL` to `.env.template`. Modifies Dockerfile layers (`docker/base/CPU_ML_base/Dockerfile`, `docker/base/GPU_ML_base/Dockerfile`). Adds `core-nlp-requirements.txt`.

- **newretrieval-fixes**: Modifies GPU base image, devcontainer, and Dockerfiles but does NOT add new environment variables. Suggests using Docker profiles instead.

**Impact**: If you merge, ensure the new environment variables are properly injected into the NLP service's build context.

---

## Recommended Merge Strategy

### Option A: **Merge newretrieval-fixes into refactor/nlp** (Recommended)

1. **Reason**: refactor/nlp is the more significant refactor. You want to keep its new architecture (ModelManager, ClaimExtraction) but gain the retrieval and scraper fixes.

2. **Steps**:
   - Start the merge (already did: `git merge origin/newretrieval-fixes`)
   - Resolve each conflict in order:
     - **`.gitignore`**: Take both additions
     - **`.env.template`**: Decide: keep new model vars (refactor/nlp) or deprecate (newretrieval-fixes)? Based on config.py usage.
     - **`docker-compose.yml`**: Clarify network strategy. If external, adjust refactor/nlp's approach. If compose-managed, keep refactor/nlp's way.
     - **`preprocess.py`**: Manually merge both approaches (use phases from newretrieval-fixes, add junk patterns, keep photo credit guard from refactor/nlp).
     - **`nlp_service.py`**: Take both (keep GPU logging + keep refactor/nlp's options assignment).
   - Run `git add` on each resolved file
   - Create a merge commit with a clear message explaining the resolution

3. **Validation after merge**:
   - Run `pytest tests/` to ensure no broken imports
   - Run E2E pipeline test with a real article
   - Check that NLP models load correctly with new ModelManager
   - Verify that scraper output feeds correctly into new NLP pipeline

### Option B: **Cherry-pick from newretrieval-fixes** (Conservative)

1. **Reason**: If you're unsure about the merge, pick only the high-value retrieval and scraper fixes without merging the branches.

2. **Steps**:
   - Identify key commits from newretrieval-fixes (e.g., "fix parser author/date extraction", "API code now sets news_outlet")
   - Use `git cherry-pick <commit>` to apply just those changes
   - Manually resolve any conflicts at the commit level

3. **Pros**: Lower risk, more controlled
4. **Cons**: Requires identifying which commits matter; may miss dependencies

---

## Conflict Resolution Checklist

### Before you merge:

- [ ] Understand which NLP model variables are actually used by `microservices/nlp/config.py`
- [ ] Clarify deployment strategy: is `sentinel-net` external or compose-managed?
- [ ] Review what scraper fields the new NLP pipeline expects
- [ ] Check if NLPResult schema changes break retrieval layer

### During merge:

- [ ] Use `git mergetool` or manual editing for each conflicted file
- [ ] Test compilation/imports after each conflict resolution
- [ ] Stage resolved files incrementally with `git add`

### After merge:

- [ ] Run linting: `./scripts/format_and_lint.sh`
- [ ] Run unit tests: `pytest tests/`
- [ ] Run E2E pipeline test with real articles
- [ ] Verify all services start: `docker-compose up`
- [ ] Check Redis stream schemas match both sides

---

## Commit Summaries

**refactor/nlp** (commits since merge base):
- `18acccd model manager`
- `f87124a gpu manager implemented`
- `1819e55 checkpoint, rewired nlp`
- `823d639 feat(nlp): integrate features/nlp pipeline architecture with ModelManager`
- `49f2207 model manager implemented`

**newretrieval-fixes** (commits since merge base):
- `adc9e9f fix: api code now sets news_outlet before db and before publishing`
- `38c1bf1 Merge branch 'newretrieval-fixes'`
- `d001d40 feat: refactor and clean up stats`
- `6a8da16 Fix parser author/date extraction for all outlets, add ISO date normalisation, add outlet matching to scraper/API/ingestor`
- `debefff Delete C:UsersSadiq.wslconfig`

---

## Files Changed (non-conflicting)

### refactor/nlp only:
- `common/model_manager/` — new ModelManager framework
- `microservices/nlp/components/claimextract.py` — new unified pipeline orchestrator
- `microservices/nlp/components/sentenceextract.py` — new sentence extraction
- `microservices/nlp/tests/debug_articles/` — new test articles and debug scripts
- `microservices/nlp/models/base.py` — refactored base classes
- Removes: `microservices/nlp/tests/pipeline.ipynb`, `test_output_article2.json`, `registry.py`

### newretrieval-fixes only:
- `microservices/web_scraper/parsers/` — all parser improvements (BBC, CBS, Guardian, NPR, etc.)
- `microservices/api/app/services/news_outlet.py` — new news outlet service
- `microservices/ingestor/base_ingestor.py` — refactored ingestor
- `scripts/database/merge_and_rebuild_streams.py` — new stream debugging script
- `microservices/api/app/crud/crud_article.py` — CRUD improvements

These non-conflicting changes should merge cleanly once the 5 conflicted files are resolved.

---

## Conclusion

**Merge is possible but requires careful manual resolution of 5 conflicted files.** The conflicts are not trivial — they reflect architectural decisions (network setup, NLP model configuration, preprocessing strategy). Before merging, ensure:

1. **Config alignment**: Verify NLP model variables are correct in config.py
2. **Network strategy**: Decide on network management in docker-compose
3. **Preprocessing robustness**: Merge both preprocessing strategies thoughtfully
4. **E2E validation**: Test the full pipeline after merge

**Estimated effort**: 2–3 hours of careful manual resolution + 1 hour testing.

**Risk level**: Medium-to-high due to architectural divergence. Both branches touch core NLP logic but from different angles.
