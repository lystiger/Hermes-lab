# Sprint 05 — Operational API hardening

Review the integrated Antigravity scaffold and `HANDOFF_AGY.md`.

Replace placeholder metrics with process-local behavior:

- monotonic non-negative integer uptime;
- concurrency-safe request counting;
- a count visible from `/metrics` that includes the current metrics request;
- no regression to `/health`, `/version`, `/info`, or `/ready`.

The final contracts require `/info` to expose application name, version, and
environment; `/ready` to return `{"status": "ready"}`; and `/metrics` to return
non-negative integer `uptime_seconds` and `requests_handled` values whose count
never decreases during one process lifetime.

Keep the implementation small and dependency-free. Add deterministic tests for
runtime behavior and update `HANDOFF_CLAUDE.md` with design choices, changed
files, test results, and remaining verification risks.

Do not commit, merge, rebase, push, edit Git metadata, or operate outside this
assigned worktree. The controller owns all Git operations.
