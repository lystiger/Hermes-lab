# Sprint S07 — Builder file ownership: independent verification

Independently verify the ownership and parallel-group changes in
`runner/run-hermes-sprint.py`. You do not modify target source; you report.

Check, with evidence from the code and the test run:

- every rule in `prompts/s07-agy.md` is implemented, and each is covered by a
  test that would fail if the rule were removed;
- the boundary `backend/` versus `backend2/` is handled;
- overlapping prefixes inside one `parallel_group` are rejected at load time,
  before any worktree is created;
- `FAILED_OUTSIDE_OWNERSHIP` is raised before commit and merge, and the
  integration branch is not touched on failure;
- phases without `owned_paths` behave exactly as before;
- verifier phases still reject any target change;
- `parallel_group` does not change execution order (phases still run in
  sequence).

Run `tests/test_runner_ownership.py` and the existing runner tests. Report each
check as PASS, FAIL or UNPROVEN with the command and result that supports it.

Replace `HANDOFF_S07_CODEX.md` with the check list, the commands you ran and
their results, and the remaining risks.

Do not commit, merge, rebase, push, edit Git metadata, or operate outside this
assigned worktree. The controller owns all Git operations.
