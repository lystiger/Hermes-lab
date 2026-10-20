# LysControl persona-core hardener

Review the builder's change (see the builder prompt). Look for concrete defects only: an image reference still in source or tests, a component that now renders an empty box or a broken image instead of the fallback, a deleted test instead of a changed one, lost text, and layout that changes at 900 px.

Fix only concrete defects, each with a test. Run the four gates. Write HANDOFF_HARDENER.md with each defect and fix, or "none". Commit only if you changed files, with the trailer `Co-Authored-By: Claude Haiku 5.5 <noreply@anthropic.com>`. Leave the handoff untracked.

Do not use git stash, git checkout on existing files, or git reset. Do not change other worktrees.
