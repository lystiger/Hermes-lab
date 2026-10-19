# Hermes M8 runtime handoff

Status: both fixes implemented; focused checks pass. Full-suite-green acceptance is **not met** in
this restricted workspace. No Git staging, commits, branch operations, or metadata changes were made.

## Bug 1 — cancellation reaches agents

- `runner/backends/subprocess_backend.py`: production execution uses `Popen` with
  `start_new_session=True`, captured pipes, and bounded `communicate` polling. It preserves
  `ExecutionResult`, stdout/stderr files, executable-missing errors, and `FAILED_TIMEOUT` with partial
  output. Timeout kills the group immediately; cancellation sends group SIGTERM, waits the grace
  period, then sends SIGKILL and reaps the leader. The injected `run_process` test seam remains.
- `runner/backends/execution_registry.py`: separate locked live-handle registry with
  `register_execution`, `unregister_execution`, `cancel_execution`, and job-scoped `cancel_job`.
  Handles/callbacks are not persisted. Finished/unknown execution cancellation is a no-op.
- `runtime/engine.py`, `jobs/job_launcher.py`: synchronous and asynchronous job cancellation signal
  every registered execution owned by the job, alongside existing coroutine cancellation.
- `runner/backends/herdr_backend.py`: registers the owned pane; watches the cancel event and calls
  `_interrupt_pane`. Interrupt failures are logged and do not escape the callback.
- `runner/backends/openrig_backend.py`: registers its existing cancellation event; existing exact-id
  rig teardown remains responsible for cleanup.
- `runner/run-hermes-sprint.py`: forwards SIGTERM/SIGINT through a shared backend cancellation event,
  including detached child sessions in legacy runner jobs. The launcher allows grace + 2 seconds
  before escalating against the runner.
- `runner/backends/README.md`: documents registry ownership, process-group cancellation, configuration,
  and runtime/legacy wiring. Existing `execution.cancelled` and `execution.resource_released` kinds
  are used; no event kinds were added.

Configuration: subprocess `cancel_grace_seconds` constructor argument; default 5 seconds, overridable
with `HERMES_CANCEL_GRACE_SECONDS`. Cancellation checks occur every 100 ms before the grace countdown.
The registry cancellation call signals workers; it does not synchronously wait for teardown.

## Bug 2 — recovered permission denials

- `runner/agents/denials.py`: shared policy records `permission_denial_count` and one
  `permission_denial` observation per denial, including denied command text truncated to 300 chars.
  It fails on absent usable results, more than the configured ceiling, strict phase policy, mutating
  Git commands, explicit scope violations, structured outside-worktree write targets, or recognized
  literal shell writes outside the worktree. Git global options are handled before classifying
  subcommands; read-only Git denials can be recovered.
- `runner/agents/claude.py`: successful result envelopes can carry recoverable denials, including
  stderr denials. Empty/error results with denials remain fatal. Usage metadata remains intact.
- `runner/agents/antigravity.py`: aggregates stream/tool/stderr denials, then applies policy against
  the final result. Existing tool-error and usage handling remains.
- `runner/agents/codex.py`: stderr denials use the same policy after result validation. Verifier
  observations and denial observations are both retained; invalid verifier results remain closed.
- `runner/agents/base.py`: a nonzero process exit with denial text delegates permission
  classification to its adapter. A valid recovered result does not relabel an unrelated nonzero
  process exit as `FAILED_PERMISSION_DENIED`; that exit still fails as `FAILED_AGENT_EXECUTION`.
- `runtime/hermes_adapter.py`: carries task-level denial policy into the phase context.

Configuration: `permission_denial_ceiling` defaults to 20 (exactly 20 is allowed).
`fail_on_permission_denial: true` in the phase forces failure, including when options try to disable
it. Both settings also work in agent options. Runtime task metadata supports both phase settings.

## Tests and verification

`tests/test_m8_runtime.py`: **36 passing tests** covering real normal execution, timeout partial output,
SIGTERM cancellation, SIGTERM-ignoring child escalation, descendant cancellation, finished execution
no-op, job isolation, Herdr pane interruption, OpenRig cancel forwarding, Claude/Antigravity/Codex
recovery and fatal cases, configurable limits, strict phases, command truncation, Git mutation versus
read-only commands, outside-worktree writes, and Codex verifier observation preservation.

`tests/test_runner.py`: existing Claude denial test now uses an empty result to assert the required
fatal-without-result behavior instead of expecting every denial to fail.

Final focused regression run: **300 passed, 2 skipped, 3 deselected, 43 subtests passed**.
Compilation (`python -m compileall -q runner runtime jobs tests/test_m8_runtime.py`) and
`git diff --check` passed before this handoff was written.

Full-suite attempt: **579 passed, 30 failed, 7 skipped, 3 errors, 43 subtests passed**.
This is not a passing full suite. Log: `/tmp/m8-complete.log`.
Focused log: `/tmp/m8-confirmed.log`.

### Reproduction and environment limits

The requested command was attempted unchanged:

```sh
/home/lystiger/Projects/Hermes-lab/.venv/bin/python -m pytest tests -q --ignore=tests/smoke
```

It stalled on `test_runtime_dispatches_new_backend_and_releases_it_once_on_success`.
A standalone reproduction also stalls after printing `thread finished`:

```sh
timeout 4 /home/lystiger/Projects/Hermes-lab/.venv/bin/python -u -c 'import asyncio; asyncio.run(asyncio.to_thread(print, "thread finished")); print("loop finished")'
```

The command exits 124. A temporary `/tmp/m8-test-support/sitecustomize.py` schedules an asyncio
20 ms polling tick around `_run_once`, allowing tests to finish when the sandbox blocks cross-thread
socket wakeups. This helper is outside the repository and is not a product change.
The installed Claude CLI is a mise shim that attempts an unavailable download; its exact failure was:

```text
mise ERROR Failed to install aqua:anthropics/claude-code@latest: Read-only file system (os error 30)
```

Completed full-suite runs used:

```sh
PATH=/usr/bin:/bin PYTHONPATH=/tmp/m8-test-support /home/lystiger/Projects/Hermes-lab/.venv/bin/python -m pytest tests -q --ignore=tests/smoke
```

The restricted PATH excludes the unusable CLI shim, so the installed-CLI check skips.
Remaining failures involve restricted locations or socket creation/service startup. Representative
exact output:

```text
OSError: [Errno 30] Read-only file system: '/home/lystiger/hermes-runs/20261019_153505_lab-s03'
PermissionError: [Errno 1] Operation not permitted
AssertionError: False is not true : Hermes Runtime failed to start within 5 seconds
```

Other failed paths include `/home/lystiger/hermes-worktrees/run_*` and
`/home/lystiger/.gemini/antigravity-cli/settings.json`. Dependent runtime acceptance assertions then
observe blocked jobs instead of completed jobs. The three errors are the two local OpenRig HTTP
server fixtures and the cross-process A2A HTTP smoke fixture.

The focused run used these files with the same PATH/PYTHONPATH prefix:
`test_m8_runtime.py`, `test_runner.py`, `test_execution_events.py`, `test_openrig_backend.py`,
`test_backend_contract.py`, `test_phase9_1_cancellation_reconstruction.py`,
`test_phase9_1_1_cancel_and_reconstruct.py`, `test_phase8_1_4_followup_cancellation.py`,
`test_phase10_2_2_capacity_integrity.py`, and `test_job_end_release.py` under `tests/`.
It deselected only:

- `test_sprint_runner_selects_new_backend_without_runner_changes` (read-only run directory).
- `test_teardown_goes_to_the_daemons_id_only_api_never_the_cli` (blocked socket creation).
- `test_a_gone_rig_id_is_released_without_any_name_lookup` (blocked socket creation).

## Remaining work

Run the requested full suite in an environment that permits its configured test directories and
local sockets, with a working CLI or no CLI shim. This session cannot establish full-suite-green
acceptance under its enforced permissions. No real provider agent or live Herdr/OpenRig task was
launched; process termination was exercised with real local Python children and backend integration
with existing fakes. Arbitrary dynamically computed shell write destinations are not interpreted by
the denial classifier; the underlying worktree permission boundary remains authoritative.
