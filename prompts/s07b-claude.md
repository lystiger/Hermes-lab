# Sprint S07b — Harden builder file ownership

You are the HARDENER. The builder change in `runner/run-hermes-sprint.py` and
its tests are already in this worktree. An independent verifier found the
defects below. Fix only these concrete defects, with tests. Do not redesign,
do not restyle, do not refactor.

## Defects to fix, in order

1. **Changed-file paths are mis-parsed.** `inspect_changed_files` calls
   `.strip()` on the whole `git status --porcelain` output, so the first line
   loses its leading space. `_enforce_phase_ownership` then reads `line[3:]`,
   which turns `" M backend/api.py"` into `"ackend/api.py"` and rejects an
   in-bounds change. Fix the parsing so each porcelain line is handled without
   losing its status columns. Add a test with a real unstaged modification
   inside `owned_paths` that must succeed.
2. **Renames ignore the source path.** A rename from outside `owned_paths` into
   `owned_paths` must fail with `FAILED_OUTSIDE_OWNERSHIP`, because the source
   deletion is outside ownership. Add a test.
3. **Overlap is not rejected at load time.** Overlapping `owned_paths` inside
   one `parallel_group` must raise before any worktree is created. Check the
   load path, not only `validate_execution_plan`. Add a test.
4. **Non-list `owned_paths` crash.** Values such as `123` or `True` raise
   `TypeError`. They must raise the sprint validation error instead. Add tests
   for both.
5. **Ownership runs too late.** Spec ownership validation must run before any
   worktree is created or agent started. Add a test that proves no worktree
   setup happens for an invalid spec.
6. **`test_codex_command_is_non_interactive_and_scoped` depends on a gitignored
   file.** `runner/agents/base.py` reads model options from
   `config/agent_models.json` through `agent_models.model_registry`, and that
   file is absent in worktrees. Make this test hermetic: it must produce the
   same command with or without the local config. Do not commit that config
   file.

## Rules

- Keep each fix local to the function it concerns. No new abstractions.
- Keep `tests/test_runner_ownership.py` as the spec. You may add tests; do not
  weaken or delete existing ones.
- Run only single, plain test commands with no pipes, `;`, `&&`, `||`,
  `sed`, or redirection:
  - `python3 -m unittest tests.test_runner_ownership`
  - `python3 -m unittest tests.test_runner`
- Do not run any git command, including `git status`, `git diff`,
  `git stash` and `git log`. Use your file-reading tools to inspect changes.
- Edit files with your file-editing tools, not with `sed -i`.
- Do not create files outside the defects above.

## Handoff

Replace `HANDOFF_S07B_CLAUDE.md` with, for each defect 1 to 6: the status
(fixed, or not fixed with the reason), the test that covers it, and the
function you changed. Name anything you could not run.

Do not commit, merge, rebase, push, edit Git metadata, or operate outside this
assigned worktree. The controller owns all Git operations.
