# Sprint S07 — Builder file ownership: implementation

Implement builder file ownership and parallel-group validation in
`runner/run-hermes-sprint.py`, so that the contract tests in
`tests/test_runner_ownership.py` pass. That file was written by the previous
phase and is the specification. Do not weaken or delete its tests; change them
only if they contradict the rules stated in `prompts/s07-agy.md`, and say so in
your handoff.

Rules to implement (see `prompts/s07-agy.md` for the full wording):

- Validate `owned_paths` and `parallel_group` when the sprint spec is loaded.
  Reject invalid values and overlapping prefixes inside one `parallel_group`
  before any worktree is created or agent is started.
- Enforce ownership after a builder phase finishes. Changed files outside
  `owned_paths` fail the phase with `FAILED_OUTSIDE_OWNERSHIP`, before commit or
  merge. Reuse the existing changed-file inspection; do not add a second git
  call path.
- Keep phases without `owned_paths` on the current code path.
- Verifier phases keep forbidding target changes.

Constraints:

- Parallel execution is out of scope. `parallel_group` is validated only; phases
  still run sequentially. Say so in the code comment next to the group check.
- Match the file's existing style: its status-code helpers, error messages and
  logging. Keep the diff small and local to the validation and phase-completion
  paths.
- Update `runner/README.md` with one short section on `owned_paths` and
  `parallel_group`, next to the existing role documentation.

Run `tests/test_runner_ownership.py` and the existing runner tests. Replace
`HANDOFF_S07_CLAUDE.md` with: the changed functions, the test results you
observed, and any test you changed and why.

Do not commit, merge, rebase, push, edit Git metadata, or operate outside this
assigned worktree. The controller owns all Git operations.
