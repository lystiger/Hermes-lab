# Sprint 06 — Independent session backend verification

Independently verify the integrated `herdr-session` backend while your phase is
hosted through the existing one-shot Herdr backend.

Focus on:

- Codex-only support and forced `workspace-write` startup arguments;
- exact Herdr CLI syntax and JSON response parsing;
- opaque workspace, pane, and agent identifiers;
- settled, blocked, unknown, stalled, and timeout lifecycle behavior;
- transcript persistence and non-empty Codex result validation;
- targeted interruption and cleanup of only owned resources;
- unchanged subprocess, one-shot Herdr, controller Git, and worktree gates.

Run a harmless live session smoke only when `HERDR_ENV=1` and the server is
reachable. Never control or close pre-existing workspaces, panes, agents, or
sessions. Add only evidence-supported fixes and focused tests. Replace
`HANDOFF_CODEX.md` with commands, results, and remaining risks.

Do not commit, merge, rebase, push, edit Git metadata, or operate outside this
assigned worktree. The controller owns all Git operations.
