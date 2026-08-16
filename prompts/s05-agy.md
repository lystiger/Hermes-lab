# Sprint 05 — Operational API scaffold

Implement the mechanical scaffold for the Sprint 05 operational API described
below.

1. Add `GET /info` returning application name, version, and environment.
2. Add `GET /ready` returning HTTP 200 and `{"status": "ready"}`.
3. Add `GET /metrics` with the required `uptime_seconds` and
   `requests_handled` integer fields. Use simple deterministic placeholder
   values in this scaffold; Claude owns live runtime-state hardening.
4. Add focused endpoint tests while preserving all existing tests.
5. Replace `HANDOFF_AGY.md` with Sprint 05 changes, verification commands, and
   explicit pending hardening work.

Do not implement persistence, Prometheus output, authentication, or new
dependencies. Do not commit, merge, rebase, push, edit Git metadata, or operate
outside this assigned worktree. The controller owns all Git operations.

Headless command permissions are intentionally narrow. When terminal execution
is needed, use only `pwd`, `ls -la`, or `python3 -m pytest -q`; do not combine
commands or add shell operators.
