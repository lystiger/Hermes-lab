# Sprint S07 — Builder file ownership: contract tests

Write the failing tests that specify builder file ownership and parallel
groups in the sprint runner. Do not change `runner/run-hermes-sprint.py`; the
next phase implements it.

Specify these rules in a new file `tests/test_runner_ownership.py`:

1. A phase may declare `owned_paths`: a list of non-empty relative path
   prefixes inside the worktree (for example `backend/`, `frontend/app/`).
   Absolute paths, `..` segments and empty strings are invalid.
2. A phase may declare `parallel_group`: a non-empty string. Phases that share a
   group must have non-overlapping `owned_paths`. Two prefixes overlap when one
   equals the other or one is a path prefix of the other at a `/` boundary
   (`backend/` overlaps `backend/app/`; `backend/` does not overlap `backend2/`).
3. A phase that declares `parallel_group` must also declare `owned_paths`.
4. A builder phase with `owned_paths` that changes a file outside those prefixes
   must fail with the status `FAILED_OUTSIDE_OWNERSHIP`. The failure names the
   file's path relative to the worktree.
5. Phases without `owned_paths` keep the current behaviour unchanged.
6. Verifier phases still forbid any target change, regardless of ownership.

Test the rules through the public functions or the sprint controller the
runner already exposes, following the style of `tests/test_runner.py`. Read that
file first. Cover valid specs, every invalid case above, the boundary case
`backend/` versus `backend2/`, and the unchanged legacy behaviour.

Tests must fail for the right reason today (missing feature), not because of
syntax or import errors. Keep the change to that one test file.

Replace `HANDOFF_S07_AGY.md` with: the test cases you wrote, the rule each one
covers, and which tests you expect to fail before the implementation exists.

Do not commit, merge, rebase, push, edit Git metadata, or operate outside this
assigned worktree. The controller owns all Git operations.
