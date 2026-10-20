# Hermes M11 hardener

Review the builder's durable job change (see the builder prompt). Look for concrete defects only: a state change that is not persisted, a partial record after a crash (non-atomic write), a restart that loses a job it should keep, a run folder loaded twice, an interrupted job left in a running status, a response shape change, and a test that passes for the wrong reason.
Fix only concrete defects, each with a test. Run the pytest gate with the venv. Write HANDOFF_HARDENER.md listing each defect and fix (or "none"). Commit with the trailer `Co-Authored-By: Claude Haiku 5.5 <noreply@anthropic.com>` only if you changed files.
Do not use git stash, git checkout on existing files, or git reset.
