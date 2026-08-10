Implement a small S03.1 hardening pass on the current Hermes-lab.

Do NOT redesign the architecture and do NOT start the Herdr backend migration yet.

Repository:
~/hermes-lab

Current state:
- Sprint 03 agent adapter architecture is already implemented.
- Supported workers: Antigravity, Claude, Codex.
- Python controller owns orchestration, validation, Git integration, and final promotion.
- Existing test suite currently passes.
- Preserve Sprint 02/Sprint 03 compatibility.

Fix these four issues only:

1. DETERMINISTIC SPRINT RERUNS

Existing worktrees can retain commits/state from a previous execution.

Make every sprint execution start from deterministic branch state.

Required behavior:
- canonical repo must still be clean;
- integration worktree must start from the configured base branch;
- phase worktrees must start from the correct integration state;
- phase 1 must not accidentally reuse an old worker branch state;
- later phases must continue to sync from the latest integration result;
- rerunning the same sprint should not depend on previous local worker commits.

Be careful with existing Git worktrees and branches.
Do not delete user data blindly.

Add regression tests proving a repeated run initializes/synchronizes phase worktrees correctly.

2. STOP TESTS TOUCHING LIVE ANTIGRAVITY CONFIG

Current permission code/tests use:

~/.gemini/antigravity-cli/settings.json

directly.

Refactor scoped_antigravity_permissions so the settings path is injectable.

Production default should still resolve to the real user config, preferably using:

Path.home() / ".gemini/antigravity-cli/settings.json"

Tests MUST use temporary files/directories and must never mutate the actual ~/.gemini configuration.

Preserve exact restoration semantics for:
- success
- exception
- timeout
- initially missing settings file

3. HARDEN CONTROLLER-ONLY GIT OWNERSHIP

The architecture says workers edit files while the controller owns:

git add
git commit
git merge
git rebase
git push
branch/ref manipulation

Currently this is partly prompt policy.

Strengthen worker-level enforcement where the CLI supports it.

Requirements:
- preserve Antigravity's existing .git write protections;
- Codex must remain sandboxed to its assigned workspace;
- Claude should receive explicit permission/tool restrictions preventing Git mutation commands where practical;
- do not block harmless read-only Git inspection such as:
  git status
  git diff
  git log
  git branch --show-current
  git rev-parse

Do not rely solely on prompt text for Git mutation protection.

Keep the controller itself fully able to perform its Git operations.

Add focused tests for the resulting command/config behavior.

4. SANITIZED RUN EVIDENCE

Add an optional deterministic sprint-result artifact suitable for committing or inspecting later.

Do NOT persist raw model prompts, stdout, stderr, secrets, tokens, or conversation content.

Produce something like:

reports/<sprint-id>/run-summary.json

or another clean equivalent containing only safe structured information such as:

{
  "sprint_id": "...",
  "status": "READY_FOR_REVIEW",
  "phases": [
    {
      "phase": "...",
      "agent": "...",
      "status": "SUCCESS",
      "changed_files_count": 5
    }
  ],
  "test_status": "PASSED",
  "integration_commit": "..."
}

Avoid machine-specific absolute paths where possible.

If persisting this automatically would contaminate the worker changed-file validation or create awkward Git behavior, implement it as an explicit controller finalization/export step and document the behavior.

IMPORTANT INVARIANTS

Do not weaken:
- FAILED_DIRTY_REPO
- worktree branch validation
- changed-file limit
- handoff requirement
- Python syntax validation
- agent result validation
- timeout handling
- isolated pytest execution
- READY_FOR_REVIEW test gate
- controller-only commits and merges

Do not:
- implement Herdr execution;
- implement persistent agent panes;
- introduce parallel execution;
- introduce an LLM orchestrator;
- allow agents to commit;
- push anything to origin;
- merge to main;
- broadly refactor unrelated FastAPI code.

TESTING

Add regression tests for all changes.

Run the complete suite.

Expected result:
- existing tests remain green;
- new hardening tests pass;
- no test touches real ~/.gemini config;
- rerunning the same sprint is deterministic;
- worker Git mutation boundaries are stronger;
- sanitized run evidence is generated without leaking agent output.

Before finishing:
1. inspect the complete diff;
2. run pytest;
3. summarize any behavior changes;
4. write/update HANDOFF_CLAUDE.md with:
   - files changed
   - invariants preserved
   - tests run/results
   - remaining risks

Do not commit, merge, rebase, push, or modify Git metadata.
The sprint controller owns Git operations.