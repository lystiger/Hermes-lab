# Hermes Lab — Sprint 05

## Three-Agent Operational API Delivery

**Sprint ID:** `lab-s05`  
**Baseline:** `ae984e1a8cda766143a8c3e01dfeeef549d59ac2`  
**Workers:** Antigravity, Claude, Codex

## Goal

Deliver a small operational API slice while proving that all three registered
workers can contribute through the same controller-governed pipeline.

The final integration branch must provide:

- `GET /info` with application name, version, and environment;
- `GET /ready` with an explicit readiness result;
- `GET /metrics` with non-negative integer uptime and request-count values;
- regression tests preserving `/health` and `/version`;
- successful full-suite validation and final `READY_FOR_REVIEW` status.

## Agent ownership

### Antigravity — scaffold

Antigravity owns mechanical endpoint and test scaffolding. It runs through the
Herdr backend to prove that scoped Antigravity permissions survive remote pane
hosting. It must update `HANDOFF_AGY.md` and leave runtime hardening to Claude.

### Claude — harden

Claude reviews the integrated scaffold through the subprocess reference
backend. It replaces placeholder metrics with process-local monotonic uptime
and concurrency-safe request counting, expands tests, and updates
`HANDOFF_CLAUDE.md`.

### Codex — verify

Codex independently verifies the integrated result through Herdr. It adds only
evidence-supported regression coverage or narrow fixes, runs the full suite,
and updates `HANDOFF_CODEX.md`.

## Execution topology

```text
Pinned Sprint 04 baseline
        |
        v
Antigravity scaffold (Herdr)
        |
        v
Claude hardening (subprocess)
        |
        v
Codex verification (Herdr)
        |
        v
Controller integration tests
        |
        v
READY_FOR_REVIEW
```

The controller remains the only owner of Git staging, commits, merges,
worktree resets, integration tests, and final status.

## Acceptance contract

- `/info` returns `app`, `version`, and `environment` fields.
- Default environment is `development`; configuration must be documented and
  tested if an override is supported.
- `/ready` returns HTTP 200 and `{"status": "ready"}`.
- `/metrics` returns integer `uptime_seconds >= 0` and
  `requests_handled >= 1`.
- Request count never decreases during one process lifetime.
- Existing `/health` and `/version` contracts remain unchanged.
- No worker performs Git mutation or operates outside its assigned worktree.
- The complete integration test suite passes.

## Non-goals

- Prometheus text exposition;
- persistent or distributed metrics;
- authentication, deployment, or production monitoring;
- interactive Herdr `agent start` / `agent prompt` semantics;
- a new adapter, backend, framework, or dependency.

## Run

Start from a Herdr-managed pane:

```bash
python3 runner/run-hermes-sprint.py --spec sprints/lab-s05.json
```

Success is the generated summary status `READY_FOR_REVIEW`.
