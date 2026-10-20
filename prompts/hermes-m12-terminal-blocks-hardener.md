# Hermes M12 hardener

Review the builder's change (see the builder prompt). Look for concrete defects: a real code defect that is now wrongly treated as environment-blocked (which would hide a bug), a repairable verdict that now ends the job, a verdict field that is lost during parsing, a test that passes for the wrong reason, and a response-shape change. Fix only concrete defects, each with a test.

Run the pytest gate with the venv. Write HANDOFF_HARDENER.md with each defect and fix (or "none"). Commit only if you changed files, with the trailer `Co-Authored-By: Claude Haiku 5.5 <noreply@anthropic.com>`. Leave HANDOFF_HARDENER.md untracked.

Do not use git stash, git checkout on existing files, or git reset. Do not run commands that modify other worktrees.
