# Sprint 03.1 Hardening Handoff

## Files changed

- `runner/run-hermes-sprint.py`: deterministic worktree resets and optional sanitized report export.
- `runner/agents/permissions.py`: injectable Antigravity settings path with a home-directory production default.
- `runner/agents/antigravity.py`: adapter-level injection of the settings path.
- `runner/agents/claude.py`: mandatory CLI denials for Git mutation commands.
- `runner/agents/codex.py`: enforced `workspace-write` sandbox.
- `tests/test_runner.py`: isolated permission, rerun, worker-boundary, and sanitized-report regression tests.
- `runner/README.md`: documented rerun and report behavior.

## Behavior changes

- Every clean, correctly assigned integration or phase worktree is reset to its configured starting ref during environment preparation. Dirty and wrong-branch worktrees still fail before any reset.
- Later phases still synchronize from the newest integration commit.
- Tests never read or modify live Antigravity settings.
- Claude blocks common Git mutation and ref-changing commands through `--disallowed-tools`; harmless inspection remains available.
- Codex sprint options cannot select a weaker sandbox.
- `--export-report [PATH]` emits safe deterministic evidence after execution. With no path it writes `reports/<sprint-id>/run-summary.json`.

## Invariants preserved

- Sprint 02 and Sprint 03 specifications remain supported.
- Canonical dirty-repository, worktree branch, changed-file, handoff, syntax, timeout, and agent-result checks remain fail-fast.
- The controller alone stages, commits, resets, and merges.
- Pytest still runs in an isolated environment and remains mandatory for `READY_FOR_REVIEW`.

## Tests

`pytest -q`: **39 passed** in the repository's isolated virtual environment.

One existing dependency warning remains: Starlette deprecates the `httpx`-backed compatibility import currently used by `fastapi.testclient`. It does not affect the S03.1 results.

## Remaining risks

- Claude CLI command-pattern restrictions are defense in depth rather than an operating-system sandbox; unusual shell indirection may not match a direct Git command pattern. Prompt policy remains as a secondary boundary.
- A default-path sanitized export makes the canonical repository dirty by design. It must be committed, moved, or removed before another sprint run.
