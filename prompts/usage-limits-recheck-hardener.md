# Usage limits: recheck hardener

Review the recheck builder's change (see its prompt). Look for concrete defects only: math that differs from the rules, a null shown as 0%, a secret or file path in the response, a page that recomputes the math, and a test that passes for the wrong reason.

Fix only concrete defects, each with a test. Run the Python gate with `/home/lystiger/Projects/Hermes-lab/.venv/bin/python -m pytest`. Write HANDOFF_HARDENER.md with each defect and fix (or "none"), using your file-write tool, not a shell heredoc or redirect.

Do not run git commands (add, commit, rm, stash, checkout, reset). Edit files only: the controller stages and commits your changes.
