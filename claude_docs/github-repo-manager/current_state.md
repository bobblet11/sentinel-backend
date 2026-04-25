# GitHub Repo Manager — Current Project State

**Last Updated:** 2026-03-26T07:01:15Z

---

**🔄 IMPORTANT:** After completing major work, you MUST update this file and signal the orchestrator via `claude_docs/orchestrator/agent_sync_log.md`. See `claude_docs/orchestrator/AGENT_PROTOCOLS.md` for the synchronization protocol all agents follow.

---

## Your Role
You handle all git operations: merge conflicts, creating/reverting commits, managing branches, syncing forks, resolving divergence, and executing git workflows.

## Current Branch Status

**Active Branch:** `refactor/nlp` (HEAD 823d639)  
**Main Branch:** `main` (tracking origin/main)  
**Status:** Feature branch with uncommitted changes in working directory

### Notable Recent Commits
```
823d639 feat(nlp): integrate features/nlp pipeline architecture with ModelManager
49f2207 model manager implemented
202ee55 feat(nlp): centralize model management with ModelManager
0994754 update job table to complete
8a56069 Fix retrieval service: NLI label map, entity field names, hashstore atomicity
```

## Files Currently Modified (Do Not Lose!)

```
Modified (staged and unstaged):
  common/model_manager/manager.py
  common/models/api/redis_models.py
  configs/.env.template
  docker/base/core-nlp-requirements.txt
  docker/compose/docker-compose.yml
  microservices/nlp/components/bias.py
  microservices/nlp/components/checkworthy.py
  microservices/nlp/components/claimextract.py
  microservices/nlp/config.py
  microservices/nlp/nlp_service.py
  microservices/nlp/schemas.py
  microservices/nlp/tests/debug_articles/run_pipeline_tests.py

Deleted Files (tracked):
  microservices/nlp/components/centrality.py
  microservices/nlp/components/dedupe.py
  microservices/nlp/tests/*.py, *.ipynb, *.json
```

## Critical Operations

### Before Any Merge/Rebase
1. Verify no uncommitted changes in `claude_docs/` or `.claude/agent-memory/`
2. Create backup branch: `git checkout -b backup/refactor-nlp-$(date +%s)`
3. Commit all work to feature branch first
4. Check for merge conflicts with main: `git fetch origin && git merge-base --is-ancestor main refactor/nlp`

### Commit Message Convention
```
Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
```
ALWAYS include this trailer in commit messages.

### Branch Protection Rules

⚠️ **Main branch:**
- Cannot force-push
- Requires PR review
- Status checks must pass
- No direct commits

✓ **Feature branches:**
- Can be force-pushed (during active development)
- No PR required for own work
- Merge to main when ready

## Conflict Resolution Strategy

### When Merging refactor/nlp → main

**High-Risk Files** (usually cause conflicts):
- `common/service/service_template.py` — Base class for ALL services
- `common/models/api/redis_models.py` — Inter-service schemas
- `microservices/nlp/nlp_service.py` — Service main logic
- `docker/compose/docker-compose.yml` — Service composition

**Low-Risk Files:**
- Individual NLP components (usually independent)
- Test files
- Documentation

### Merge Conflict Checklist
1. Identify conflicting files
2. For each conflict:
   - Read both versions
   - Understand what each side changed
   - **CRITICAL:** Verify both sides needed (don't delete legitimately changed code)
3. Run E2E tests after merge
4. Verify no schema mismatches between merged code

## Safety Checks Before Push

```bash
# 1. Verify no uncommitted changes
git status

# 2. Run linting
./scripts/format_and_lint.sh

# 3. Run tests
pytest tests/

# 4. Verify E2E pipeline still traceable
# (use pipeline-debugger for this)

# 5. Check for merge conflicts
git fetch origin
git merge-base --is-ancestor origin/main refactor/nlp
```

## Reference Documents

- **Git History:** Use `git log --oneline --all -- <path>` to trace file history
- **Branch Topology:** `git log --graph --oneline --all`
- **Diff Analysis:** `git diff main refactor/nlp -- <file>`
- **Commit Details:** `git show <commit-hash>`

## Known Issues

🟡 **In-Flight Refactor:** `refactor/nlp` is incomplete; don't merge to main until ModelManager integration verified  
🟡 **Test File Deletions:** Some `.ipynb` and test files deleted; verify intentional before committing  
🟡 **Schema Changes:** `redis_models.py` modified; ensure all consumers updated

---

**Remember:** Every commit changes the entire codebase's perspective. Always test E2E after merges, and always include the Copilot trailer.
