# Sprint 06 — Codex-first session backend implementation

Implement the smallest opt-in `herdr-session` backend that satisfies the
integrated Antigravity contract tests.

Requirements:

- preserve `subprocess` and one-shot `herdr` behavior;
- keep agent-specific session kind and native startup arguments owned by the
  adapter contract;
- support Codex only and preserve forced `workspace-write` isolation;
- use Herdr workspace, pane, `agent start`, `agent prompt --wait`, lifecycle
  inspection, transcript read, targeted interruption, and owned cleanup;
- parse all returned identifiers and lifecycle state from JSON;
- map blocked, unknown, timeout, protocol, command, and unsupported-agent
  failures distinctly;
- persist transcript output through the current stdout/stderr files;
- never fall back silently to one-shot execution.

The installed Herdr CLI is authoritative for exact commands and JSON shapes.
Keep changes narrow, add regression coverage, run the complete suite, and
replace `HANDOFF_CLAUDE.md` with implementation and verification details.

Do not commit, merge, rebase, push, edit Git metadata, or operate outside this
assigned worktree. The controller owns all Git operations.
