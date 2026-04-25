# Claude Docs — Agent Context Index

**Last Updated:** 2026-03-26T07:01:15Z

---

## ⚡ Agent Synchronization Protocol

**All agents must follow the synchronization protocol** defined in `claude_docs/orchestrator/AGENT_PROTOCOLS.md`. After completing major work:

1. ✅ Update your agent's `current_state.md` with a "Recent Work" section
2. ✅ Add a handoff entry to `claude_docs/orchestrator/agent_sync_log.md`
3. ✅ Flag any new constraints or critical findings

This keeps all agents synchronized and enables smooth handoffs between workflows.

---

## Agent Context Files

### 🎯 [systems-planner/current_state.md](systems-planner/current_state.md)
**Your Role:** Audit complex changes, map dependencies, assess risks, generate task plans  
**Key Focus:** NLP refactoring completion, interface blast radius, dependency tracking  
**Audience:** You are the strategic planner — verify all downstream impacts before any major change

### ⚙️ [plan-executor/current_state.md](plan-executor/current_state.md)
**Your Role:** Safely execute structured plans with dependency checking and rollback support  
**Key Focus:** File modification safety, schema immutability, rollback procedures  
**Audience:** You are the careful executor — prevent regressions through meticulous verification

### 🧪 [pipeline-debugger/current_state.md](pipeline-debugger/current_state.md)
**Your Role:** Stress-test E2E pipeline, detect regressions, generate comprehensive debug reports  
**Key Focus:** E2E traceability, dummy modes, error recovery paths, priority handling  
**Audience:** You are the regression detective — catch issues before they reach production

### 🔗 [github-repo-manager/current_state.md](github-repo-manager/current_state.md)
**Your Role:** Handle all git operations, merge conflicts, branch management, workflows  
**Key Focus:** Branch protection, conflict resolution, commit safety, merge strategies  
**Audience:** You are the repository guardian — ensure code integrity through git discipline

### 🔍 [research-and-plan/current_state.md](research-and-plan/current_state.md)
**Your Role:** Research implementation approaches, evaluate libraries/models before committing  
**Key Focus:** NLP component alternatives, schema versioning strategies, error recovery  
**Audience:** You are the solution researcher — evaluate options before planning begins

### 📚 [repo-oracle/current_state.md](repo-oracle/current_state.md)
**Your Role:** Authoritative source for repository knowledge, Docker, deployment, configuration  
**Key Focus:** Microservices inventory, environment variables, stream topology, commands  
**Audience:** You are the repository expert — answer specific questions with precision

## How to Use

**When you are assigned a task:**
1. Find your agent type above
2. Read `claude_docs/<agent>/current_state.md`
3. Use the context to understand your role and constraints
4. Reference the linked architecture documents for details

**What each file contains:**
- ✓ Your specific responsibilities
- ✓ Current project priorities relevant to your role
- ✓ Critical constraints and safety rules
- ✓ Key file locations and paths
- ✓ Reference documents for deeper context
- ✓ Known risks and pitfalls specific to your work

## Master Architecture Documents

All agents should reference these as the single source of truth:
- **Architecture:** `orchestrator/project_state.md`
- **Schemas:** `orchestrator/interface_registry.md`
- **Current Issues:** `orchestrator/drift_report.md`
- **Remediation:** `orchestrator/remediation_plan.md`

## Key Principles

🎯 **Specialized Context** — Each agent gets only information relevant to their role  
🔄 **Reference, Don't Duplicate** — Details link to authoritative sources (orchestrator/)  
⚡ **Action-Ready** — Context is structured to enable immediate, informed work  
🛡️ **Safety First** — Constraints and risks highlighted per agent role  

---

**Orchestrator Note:** These files were generated 2026-03-26T07:01:15Z as part of the full project synchronization. Update them when project state changes significantly.
