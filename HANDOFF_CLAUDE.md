# Sprint 04 Implementation Handoff

## Implemented

- Added `ExecutionRequest`, `ExecutionResult`, and `ExecutionBackend`.
- Moved reference process execution and log capture into `SubprocessBackend`.
- Added a backend registry and deterministic phase/CLI/spec/default selection.
- Added a one-shot `HerdrBackend` with executable/server preflight, JSON-only runtime ID parsing, runner-owned workspaces and panes, safe argv-array wrappers, stdout/stderr/exit capture, nonce completion detection, targeted timeout interruption, and optional owned-resource cleanup.
- Added backend and stable runtime metadata to local phase summaries; sanitized evidence includes only the backend name.
- Added the staged Sprint 04 spec and worker prompts.

## Invariants preserved

- Agent commands and result validation remain adapter-owned.
- Deterministic worktree initialization, later-phase synchronization, changed-file and handoff checks, syntax validation, controller-only Git promotion, isolated pytest, and `READY_FOR_REVIEW` remain controller-owned.
- Antigravity settings restoration, Claude `disallowedTools` Git rules, and forced Codex `workspace-write` remain unchanged.
- Explicit Herdr selection never falls back to subprocess.

## Validation

See `HANDOFF_CODEX.md` for final suite and runtime results.
