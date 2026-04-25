---
## [2026-04-01 00:01] Strengthen Automatic Agent Routing from Natural-Language Prompts

**Date**: April 1, 2026 at 12:01 AM UTC
**Agent**: `claude-inline`
**Branch**: `newretrieval-fixes`
**Triggered By**: User request to ensure agents are invoked automatically from natural-language prompts without requiring the user to specify agent names.

### Summary
Replaced the single Agent Usage table in `CLAUDE.md` with a two-part section: a "Prompt → Agent Routing" table mapping common natural-language prompt patterns to agents, plus the original full reference table. Updated four agent description files to include concrete natural-language trigger phrases so routing fires on user intent rather than explicit agent names.

### Files Changed
| File Path | Change Type | Description |
|-----------|-------------|-------------|
| `CLAUDE.md` | Modified | Replaced Agent Usage section with (1) a "Prompt → Agent Routing" table mapping prompt patterns (e.g. "commit/push/git" → github-repo-manager, "evaluate/compare/options for" → research-and-plan, "jobs are failing/something broken" → pipeline-debugger) plus a strong rule preamble requiring a match scan before any inline work; (2) the full reference table unchanged from before. |
| `.claude/agents/systems-planner.md` | Modified | Added natural-language trigger phrases ("I want to build X", "let's add X", "we need to change X", "I want to refactor X") and explicit instruction not to wait for the user to say "make a plan". |
| `.claude/agents/plan-executor.md` | Modified | Added trigger phrases ("go ahead", "do it", "apply the changes", "carry out the plan") and automatic invocation after systems-planner finishes. |
| `.claude/agents/pipeline-debugger.md` | Modified | Added symptom-based triggers ("jobs are failing", "something seems broken", "nothing is broken right") and clarified NLP-only vs E2E testing modes. |
| `.claude/agents/github-repo-manager.md` | Modified | Added all git-verb triggers ("commit", "push", "create a PR", "merge", "revert", "fix the merge conflict", "sync with main", "git"). |

### Details
- Root cause: agents were only invoked when the user explicitly named them; natural-language prompts expressing intent were falling through to inline execution.
- The two-table structure separates quick routing lookup (prompt patterns → agent) from the detailed reference (agent → description, when to use).
- Agent frontmatter descriptions now include concrete trigger phrases the harness reads when deciding whether to invoke an agent.
- No new agents were created; only CLAUDE.md routing rules and existing agent descriptions were updated.

### Pipeline Impact
None — changes are limited to `CLAUDE.md` and `.claude/agents/*.md` instruction files. No pipeline code, schemas, stream interfaces, or service logic was modified.

---
## [2026-04-01 00:00] Strengthen Agent Routing Instructions and Add Missing Agents to CLAUDE.md

**Date**: April 1, 2026 at 12:00 AM UTC
**Agent**: `claude-inline`
**Branch**: `newretrieval-fixes`
**Triggered By**: User request to update agent routing instructions — CLAUDE.md was missing 5 agents from the routing table and agent description frontmatter lacked concrete trigger conditions.

### Summary
Updated `CLAUDE.md` and four agent description files to close routing gaps: added `change-journal`, `github-repo-manager`, `research-and-plan`, `repo-oracle`, and `sentinel-orchestrator` to the Agent Usage table with precise trigger conditions. Rewrote agent frontmatter descriptions with concrete trigger words so the harness can route tasks correctly. Also corrected a stale Docker image tag in the architecture section.

### Files Changed
| File Path | Change Type | Description |
|-----------|-------------|-------------|
| `CLAUDE.md` | Modified | Added mandatory `change-journal` invocation as rule #2 in Prompt Safeguards; renumbered remaining rules. Added 5 missing agents to Agent Usage table with precise trigger conditions and a strong rule preamble. Fixed stale Docker image tag (`cuda121` → `cuda124`) in architecture section. |
| `.claude/agents/change-journal.md` | Modified | Updated description frontmatter to list every trigger scenario: post plan-executor, post systems-planner, post github-repo-manager, post research-and-plan, post pipeline-debugger, post sentinel-orchestrator, and post any inline edit. |
| `.claude/agents/research-and-plan.md` | Modified | Updated description frontmatter with concrete trigger words ("evaluate", "what are our options", "is there a better", "compare", "improve the [component]") and explicit scope covering NLP pipeline and broader architectural choices. |
| `.claude/agents/sentinel-orchestrator.md` | Modified | Updated description frontmatter with trigger phrases ("make sure everything is in sync", "agents are out of date", "starting a new sprint", "just merged a big PR") and explicit invocation scenarios. |
| `.claude/agents/repo-oracle.md` | Modified | Updated description frontmatter to clarify read-only/lookup purpose and added trigger phrases ("how does X work", "what does X do", "which service handles", "what env vars", "explain the"). |

### Details
- The primary motivation was that the harness could not route tasks to 5 agents because they were absent from the CLAUDE.md routing table entirely.
- Agent description frontmatter is what the harness reads to decide whether to invoke an agent; vague descriptions cause missed invocations or incorrect routing.
- The Docker tag fix (`cuda121` → `cuda124`) aligns the docs with the recent GPU base image upgrade committed on this branch.
- No new agents were created; only descriptions and routing rules were updated.

### Pipeline Impact
None — changes are limited to documentation (`CLAUDE.md`) and agent instruction files (`.claude/agents/*.md`). No pipeline code, schemas, stream interfaces, or service logic was modified.

---
