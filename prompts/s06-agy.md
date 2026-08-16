# Sprint 06 — Session backend contract scaffold

Create only the mechanical test scaffold for an opt-in `herdr-session` backend.
Do not implement production backend behavior.

Add focused tests covering:

- registry lookup for `herdr-session`;
- optional session data on execution requests;
- Codex session kind and forced `workspace-write` startup arguments;
- rejection of unsupported Antigravity and Claude session workers before any
  Herdr session creation;
- opaque workspace, pane, and agent identifiers;
- settled, blocked, unknown, timeout, transcript, and owned-cleanup behavior;
- preservation of existing `subprocess` and one-shot `herdr` contracts.

Tests may initially fail until Claude implements the backend, but all Python
must compile. Replace `HANDOFF_AGY.md` with the scaffolded contract, expected
failures, and verification commands.

Do not commit, merge, rebase, push, edit Git metadata, or operate outside this
assigned worktree. The controller owns all Git operations.

Headless command permissions are intentionally narrow. When terminal execution
is needed, use only `pwd`, `ls -la`, or `python3 -m pytest -q`; do not combine
commands or add shell operators.
