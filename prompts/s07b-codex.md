# Sprint S07b — Independent re-verification

Independently re-verify the builder file ownership changes after the hardener
phase. You do not modify target source; you report.

Check each item, with evidence from the code and the test runs:

1. Changed-file parsing keeps the leading status columns, so an unstaged
   modification inside `owned_paths` succeeds and no path is truncated.
2. A rename from outside `owned_paths` into `owned_paths` fails with
   `FAILED_OUTSIDE_OWNERSHIP`.
3. Overlapping prefixes in one `parallel_group` are rejected at load time,
   before any worktree is created.
4. Non-list `owned_paths` values such as `123` and `True` produce the sprint
   validation error, not a `TypeError`.
5. Ownership validation runs before any worktree setup.
6. `test_codex_command_is_non_interactive_and_scoped` produces the same result
   with and without `config/agent_models.json` present.
7. Verifier phases still reject any target change, and phases without
   `owned_paths` behave as before.

## Rules

- Run only single, plain test commands with no pipes, `;`, `&&`, `||`,
  `sed`, or redirection:
  - `python3 -m unittest tests.test_runner_ownership`
  - `python3 -m unittest tests.test_runner`
- Do not run any git command, including `git status`, `git diff`,
  `git stash` and `git log`.
- Do not create files inside this worktree other than the handoff. Keep any
  scratch notes out of the worktree.
- Do not stop at the first failure; check every item.

## Handoff

Replace `HANDOFF_S07B_CODEX.md` with one line per item 1 to 7 with PASS, FAIL
or UNPROVEN, the command or code reference that supports it, and the remaining
risks.

## Final output (required)

Your final message must be one JSON object and nothing else, with no prose
before or after it:

{"verdict": "passed" or "failed", "summary": "<one sentence>", "findings": ["<item and defect>", ...]}

Use "failed" if any item is FAIL or UNPROVEN. The runner reads this object
from your output to decide the phase result, so any other output fails the
phase.

Do not commit, merge, rebase, push, edit Git metadata, or operate outside this
assigned worktree. The controller owns all Git operations.
