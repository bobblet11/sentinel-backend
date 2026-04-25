---
## [2026-04-01 00:01] Strengthen Automatic Agent Routing from Natural-Language Prompts

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
## [2026-04-01 00:01] Rewrite Change-Journal Storage Model to File-per-Task

**Agent**: `claude-inline`
**Branch**: `newretrieval-fixes`
**Triggered By**: User requested per-task journal files instead of a monolithic CHANGELOG — new tasks get their own file, continuations prepend to the existing task file.

### Summary
The `change-journal` agent instruction file was rewritten to replace the single `CHANGELOG.md` append model with a file-per-task storage model. Each distinct task now gets its own `.md` file under `claude_docs/journal/`, and the agent prepends new entries to the matching file when a change is a continuation of the same task, or creates a new file when the task is unrelated.

### Files Changed
| File Path | Change Type | Description |
|-----------|-------------|-------------|
| `.claude/agents/change-journal.md` | Modified | Replaced "Your Core Responsibilities" and "Journal Entry Format" / "Operational Instructions" sections with a new "File-per-Task Storage Model" section describing decision logic: check for existing task file → prepend if same task, create new file if new task |

### Details
- The core storage decision logic added: (1) check `claude_docs/journal/` for a file matching the current task, (2) if found and task is a continuation, prepend the new entry; (3) if new unrelated task, create a new file named after the task slug.
- The journal entry format and operational instructions for fields (branch, files changed, pipeline impact, etc.) remain unchanged — only the file routing logic was updated.
- This entry itself is a continuation of the `add-change-journal-agent` task, so it is prepended to the existing `CHANGELOG.md` rather than creating a new file. Future distinct tasks will each get their own file.

### Pipeline Impact
None — change is limited to the agent instruction file `.claude/agents/change-journal.md`. No service code, schemas, stream definitions, or DB models were touched.

---
## [2026-04-01 00:00] Add Change-Journal Invocation Directives to All Agent Instruction Files

**Agent**: `claude-inline`
**Branch**: `newretrieval-fixes`
**Triggered By**: User requested that all agents call the `change-journal` agent after making any changes to files, to ensure a complete audit trail of all codebase and documentation modifications.

### Summary
Six agent instruction files in `.claude/agents/` were updated to include a new "Invoke change-journal After Completion" section. Each directive instructs the respective agent to delegate to the `change-journal` agent after any operation that writes, modifies, or deletes files, ensuring every agent-driven change is captured in the audit trail.

### Files Changed
| File Path | Change Type | Description |
|-----------|-------------|-------------|
| `.claude/agents/plan-executor.md` | Modified | Added change-journal invocation directive to run after execution completes (success or failure) |
| `.claude/agents/systems-planner.md` | Modified | Added change-journal invocation directive to run after writing outputs to `claude_docs/systems-planner/` |
| `.claude/agents/github-repo-manager.md` | Modified | Added change-journal invocation directive to run after git operations that modify the repository |
| `.claude/agents/research-and-plan.md` | Modified | Added change-journal invocation directive to run after writing research docs to `claude_docs/research/` |
| `.claude/agents/pipeline-debugger.md` | Modified | Added change-journal invocation directive to run after generating debug output files |
| `.claude/agents/sentinel-orchestrator.md` | Modified | Added change-journal invocation directive to run after writing orchestrator context docs |

### Details
- This change establishes a convention: every agent that produces file output is now responsible for triggering the `change-journal` agent as a final step.
- The `change-journal` agent itself is excluded from this loop to avoid circular invocation.
- No agent logic, schemas, or service code was modified — only agent instruction markdown files.
- This is the first entry in `claude_docs/journal/CHANGELOG.md`; the file and directory were created as part of this journal entry.

### Pipeline Impact
None — changes are limited to agent instruction files. No code, Pydantic schemas, Redis stream definitions, DB models, or service logic was touched. E2E pipeline stability is unaffected.

---
