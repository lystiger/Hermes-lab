# Usage limits: hardener

Review the backend and frontend changes of this sprint (see the builder prompts). Look for concrete defects only:
- The math does not match the plugin rules: fullest window decides the headline, `left = 100 − used`, balance uses `remaining / funded`, thresholds 75 and 90.
- A reset time that is wrong or shown in the past.
- A corrupt record, or a dotfile, that breaks the whole response.
- A secret, prompt, or file path that reaches the response or the page.
- A page that recomputes the math instead of displaying the backend value.
- A test that passes for the wrong reason.

Fix only concrete defects, each with a test. Run the Python gate with the venv. Write HANDOFF_HARDENER.md with each defect and fix (or "none"), using your file-write tool, not a shell heredoc or redirect.

Do not run git commands (add, commit, rm, stash, checkout, reset). Edit files only: the controller stages and commits your changes. Do not run commands that modify other worktrees.
