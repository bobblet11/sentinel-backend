# Agent Synchronization Protocol

**Effective Date:** 2026-03-26T07:05:11Z  
**Purpose:** Ensure all agents maintain synchronized context and enable efficient orchestration handoffs

## Core Protocol: The Update Cycle

Every agent must follow this lifecycle for major operations:

```
Task Assigned → Work → Complete → UPDATE CONTEXT → Ready for Handoff
```

## Definition: "Major Operation"

A major operation is any task that:
- ✓ Modifies code in more than one file
- ✓ Changes interface boundaries (stream names, DTOs, schemas)
- ✓ Adds, removes, or renames services/components
- ✓ Alters NLP pipeline order or component contracts
- ✓ Produces a plan or structure that future agents will depend on
- ✓ Fixes a bug that required understanding multiple services

**NOT a major operation:** typo fix, one-line doc update, single-file refactor with no interface change

## Mandatory Update Steps (for every major operation)

After completing work, **before marking the task done:**

### Step 1: Update Your Agent's Current State
**File:** `claude_docs/<agent-name>/current_state.md`

Add a **"Recent Work" section** at the top documenting:
- What changed
- Which files were modified
- Any new constraints discovered
- Recommended next steps for the next agent in the workflow

**Example:**
```markdown
## Recent Work (2026-03-26T14:32:00Z)

**What:** Refactored NLP Embedder to use ModelManager
**Files Modified:**
  - microservices/nlp/stages/embedder.py (interface changed)
  - common/model_manager.py (added load_embedder() method)
  - tests/nlp/test_embedder.py (updated mock strategy)

**New Constraint:** 
  - All embeddings MUST be 384-dimensional (enforced in ModelManager)
  - Dummy mode no longer generates random dims; uses hardcoded 384-dim vectors

**Next Steps:**
  - pipeline-debugger: Run E2E test with new ModelManager to verify no regressions
  - systems-planner: Audit Retrieval layer for 384-dim assumptions
```

### Step 2: Signal the Orchestrator
**File:** `claude_docs/orchestrator/agent_sync_log.md`

Add a handoff entry at the **bottom** with:
- Agent name
- Timestamp (ISO 8601)
- Operation summary (1-2 sentences)
- Link to the changed context file
- Any critical flags

**Example:**
```markdown
## 2026-03-26T14:32:00Z — plan-executor: Embedder Refactor Complete

**Changed:** `claude_docs/plan-executor/current_state.md`  
**Summary:** Refactored NLP Embedder to use new ModelManager. Interface preserved (same input/output), but internal load path changed. All tests passing.  
**Flag:** ⚠️ Embedding dimension constraint (384-dim) is now enforced in ModelManager. Retrieval layer must validate.
