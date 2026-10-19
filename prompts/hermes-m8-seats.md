# Role: BUILDER — Hermes M8, phase 2: Herdr seat pool (D-019)

You are the BUILDER and may edit source files. Hermes owns Git: do not run
git add, commit, merge, push, reset, checkout, or alter Git metadata. Work only
in your assigned worktree (the Hermes-lab repository). Run tests with
`/home/lystiger/Projects/Hermes-lab/.venv/bin/python -m pytest tests -q --ignore=tests/smoke`.
Phase 1 (cancel and denials) is already in your worktree; do not redo it.

Read `runner/backends/herdr_backend.py`, `runner/backends/README.md`,
`.agent/DECISIONS.md` (D-009, D-010) and `tests/test_backends.py`,
`tests/test_backend_contract.py`.

## Context

Today the Herdr backend makes a new pane for every phase (it splits the root
pane downward, `_create_worker_pane`) and labels it with the phase name. A job
with 3 phases gives 3 panes stacked in a column, each used once. The operator
wants fixed, named seats instead: one Herdr workspace with a set of named
panes, where any agent can run in any free seat, one agent at a time per seat.
One seat is a "hot seat": reserved for priority work, never given to normal
work.

Herdr (`herdr pane list|split|rename|run|close|…`, `herdr workspace …`) allows
panes to be reused: `herdr pane run <pane_id> <command>` runs a command in an
existing pane.

## Step 1: write the decision

Append `## D-019: Herdr seat pool (2026-10-19)` to `.agent/DECISIONS.md`
(follow the format of the entries above it). Cover: seats are named panes in
one workspace (labels `seat-1` … `seat-5`, `hot`); pool seats are assigned to
any agent; an exclusive lease per seat, released when the command ends;
waiting when no seat is free (with a timeout and a clear error); the hot seat
only takes phases with `"priority": "hot"` and may run even when all pool seats
are busy; no preemption of a running phase; a banner line written at the start
of each run in a seat (job id, phase, persona name); seats are created on first
use if missing; the long-lived sessionful hot seat is out of scope here and
listed as follow-up. State the config shape:

```json
"seat_pool": {"size": 5, "hot": true, "acquire_timeout_seconds": 600}
```

in the sprint spec or as backend settings, default off (when absent the
backend behaves exactly as today).

## Step 2: implement

- A `SeatPool` in the Herdr backend module (or a sibling): ensure workspace,
  ensure seat panes by label, lease/release with a lock, waiting with timeout,
  hot-seat rules. State survives the backend instance for a run (use the
  existing runtime file the backend writes).
- `_run_in_pane` uses a leased seat's pane instead of splitting; the seat is
  released in a `finally`, including on timeout and on cancel (phase 1 added
  cancel; interrupt the pane then release).
- Resource events (D-009): the resource id/label should be the seat label, so
  LysControl's Execution page shows seats.
- Backwards compatible: with no `seat_pool` config every existing test passes
  unchanged.
- Tests with a fake `herdr` executable (see how `tests/test_backends.py` fakes
  it): two concurrent phases get different seats; a third waits and then gets a
  released seat; acquire timeout; hot seat only for hot phases and available
  when the pool is full; release on failure and cancel; banner written;
  disabled by default.

## Done means

Full test suite passes. Write `HANDOFF_M8_SEATS.md`: what changed (files),
the config, tests, and what is left (sessionful hot seat). Stop after the
handoff.
