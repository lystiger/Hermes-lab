# Role: BUILDER — Hermes M8, phase 1: cancel and permission denials

You are the BUILDER and may edit source files. Hermes owns Git: do not run
git add, commit, merge, push, reset, checkout, or alter Git metadata. Work only
in your assigned worktree (the Hermes-lab repository).

Run tests with: `/home/lystiger/Projects/Hermes-lab/.venv/bin/python -m pytest tests -q --ignore=tests/smoke`
(the venv lives outside the worktree; the tests import the worktree's code).
Read `.agent/DECISIONS.md` (D-009, D-010 for execution events) and
`runner/backends/README.md` before changing backends.

## Bug 1: cancelling a job does not stop its agent processes

Observed: `POST /jobs/{id}/cancel` marks the job CANCELLED, but the Claude,
Codex and agy child processes keep running and keep spending provider quota.
Cause: `runner/backends/subprocess_backend.py` runs the agent with
`subprocess.run`, which gives no handle to the child, so nothing can kill it.
`jobs/job_launcher.py` `cancel_async` and `runtime/engine.py` `cancel` do not
reach the processes.

Fix:
- Run agent commands with `subprocess.Popen` in their own process group
  (`start_new_session=True`), keep the handle in the backend's execution
  registry (see `execution_registry.py`), and capture stdout/stderr and the
  timeout exactly as `subprocess.run` did (same `ExecutionResult`, same
  timeout error code, same files written).
- Add a cancel path: cancelling an execution sends SIGTERM to the whole
  process group, waits a short grace period (default 5 s, configurable), then
  SIGKILL. The job's cancel must call it for every execution the job owns.
- Emit the existing `execution.*` events (a released or failed resource with a
  cancelled reason); do not invent new event kinds without updating D-009's
  list in the README.
- Herdr and openrig backends: make cancel interrupt the pane (herdr already has
  `_interrupt_pane`) or report that it is not supported, without raising.
- Tests: a fake long-running child (for example `sleep 60` through the real
  backend) is cancelled and the process group is gone within the grace
  period; a child that ignores SIGTERM is killed; cancel on a finished
  execution is a no-op; the normal path still returns the same result and
  honours timeouts.

## Bug 2: a single denied command fails the whole phase

Observed: Claude tried a `cd …; python3 - <<EOF` command, the CLI denied it,
the agent recovered, but Hermes failed the phase with
`FAILED_PERMISSION_DENIED` (`runner/agents/claude.py` around lines 91 and
134-137, `runner/agents/base.py` around line 139, `runner/agents/antigravity.py`).

Fix: a denial must be recorded, not fatal, when the agent otherwise finished.
- Record each denial as an observation/event with the denied command text
  (truncated to 300 chars) and count.
- Fail with `FAILED_PERMISSION_DENIED` only if the agent produced no usable
  result, or the denials exceed a configurable ceiling (default 20), or the
  phase option `fail_on_permission_denial: true` is set.
- Keep the existing fail-closed behaviour for scope violations (git mutation
  denials, writes outside the worktree). A denial of a mutating git command
  stays fatal.
- Tests for each adapter that reports denials: tolerated with a result,
  fatal without a result, fatal for git-mutation denials, fatal above the
  ceiling, fatal with the option.

## Done means

The full test suite passes. Update `runner/backends/README.md` for the cancel
path. Write `HANDOFF_M8_RUNTIME.md`: per bug what changed (file), tests added,
anything not done and why. Stop after the handoff.
