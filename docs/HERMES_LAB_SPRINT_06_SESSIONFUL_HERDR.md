# Hermes Lab — Sprint 06

## Codex-First Sessionful Herdr Backend

**Sprint ID:** `lab-s06`  
**Baseline:** `565c862aef1ee5fca20adebc2883580e70030257`  
**Primary implementer:** Claude  
**Contract scaffold:** Antigravity  
**Independent verifier:** Codex

## Goal

Add an opt-in `herdr-session` backend that drives a native interactive Codex
agent through Herdr lifecycle commands. Preserve the existing `subprocess` and
one-shot `herdr` backends without behavior changes.

Sprint 06 is deliberately Codex-first. Antigravity and Claude remain on their
existing one-shot adapters until their interactive output contracts can be
defined without weakening result validation.

## Architecture boundary

```text
AgentAdapter
├── one-shot command contract
└── optional session launch contract
        |
        v
ExecutionBackend
├── subprocess
├── herdr          one-shot CLI in pane
└── herdr-session  native Herdr agent lifecycle
```

Adapters continue to own agent kind, native startup arguments, prompt, and
result validation. The session backend owns workspace and pane creation, agent
startup, prompt submission, lifecycle waiting, transcript capture, timeout
interruption, and cleanup of only its own resources.

## Agent jobs

### Antigravity — contract scaffold

- Add focused session-backend test fixtures and failing contract tests.
- Cover registration, Codex session metadata, unsupported workers, lifecycle
  state mapping, opaque IDs, and ownership boundaries.
- Do not implement production session behavior.
- Update `HANDOFF_AGY.md`.

### Claude — implementation

- Add the smallest `HerdrSessionBackend` satisfying the scaffolded contract.
- Extend execution requests only with explicit optional session data.
- Add Codex-owned session launch metadata while preserving forced
  `workspace-write` behavior.
- Keep `subprocess` and one-shot `herdr` behavior unchanged.
- Update `HANDOFF_CLAUDE.md`.

### Codex — independent verification

- Verify lifecycle transitions, transcript capture, blocked and unknown states,
  timeout interruption, opaque ID handling, and owned-resource cleanup.
- Run a harmless live session smoke test only from a Herdr-managed pane.
- Add only evidence-supported fixes and regression tests.
- Update `HANDOFF_CODEX.md`.

## Acceptance contract

- Backend registry resolves `herdr-session` explicitly.
- No specification silently falls back when `herdr-session` is unavailable.
- Only Codex is supported in session mode for Sprint 06.
- Unsupported agents fail before any session is created.
- Agent names are unique, valid Herdr names, and derived without trusting user
  text.
- Workspace, pane, and agent identifiers are parsed from JSON responses and
  treated as opaque.
- Prompt submission waits for a settled lifecycle state.
- `blocked` maps to a distinct failure and retains inspectable runtime state.
- `unknown` never counts as successful completion.
- Timeouts interrupt only the owned agent or pane.
- Transcript output is persisted to the existing stdout log contract.
- Cleanup closes only resources created by this backend instance.
- Existing one-shot backend, adapter validation, worktree, Git, and final test
  gates remain intact.
- Full suite and opt-in live Herdr session smoke pass.

## Execution constraint

The sprint controller imports backend code before worker phases run. Therefore
the Codex verification phase is hosted by the existing one-shot `herdr`
backend; it verifies the newly implemented session backend from inside its
integrated worktree. Making `herdr-session` a phase host is deferred until the
implementation has been merged into `main`.

## Non-goals

- Session mode for Antigravity or Claude;
- changing the default backend;
- cross-run session resume;
- parallel phase execution;
- automatic answers to blocked agents;
- closing pre-existing Herdr resources;
- replacing one-shot execution.

## Run

From a Herdr-managed pane:

```bash
python3 runner/run-hermes-sprint.py --spec sprints/lab-s06.json
```

Success requires `READY_FOR_REVIEW` plus a passing live session smoke test in
the integration suite.
