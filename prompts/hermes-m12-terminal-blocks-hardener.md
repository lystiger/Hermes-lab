# Hermes M12 hardener

Review the builder's change (see the builder prompt). Look for concrete defects: a real code defect that is now wrongly treated as environment-blocked (which would hide a bug), a repairable verdict that now ends the job, a verdict field that is lost during parsing, a test that passes for the wrong reason, and a response-shape change. Fix only concrete defects, each with a test.

Run the pytest gate with the venv. Write HANDOFF_HARDENER.md with each defect and fix (or "none") using your file-write tool, not a shell heredoc or redirect.

Do not run git commands (add, commit, rm, stash, checkout, reset). Edit files only: the controller stages and commits your changes. Do not run commands that modify other worktrees.
