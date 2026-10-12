# Execution backends

An execution backend hosts one worker run. Agent adapters (`runner/agents/`) decide
*what* to run: the argv, the prompt and result validation. Backends decide *where and how*
the run is hosted. Backends never touch Git, worktree promotion, scheduling or task state.
Hermes owns those.

```text
Hermes (sprint runner / ReactiveJobEngine → HermesActorAdapter)
  └── AgentAdapter.execute(context)
        └── ExecutionBackend.execute(ExecutionRequest) -> ExecutionResult
              ├── SubprocessBackend   "subprocess"  one-shot child process
              ├── HerdrBackend        "herdr"       one-shot CLI in a runner-owned persistent Herdr pane
              └── (future)            e.g. a persistent/sessionful seat runtime
```

## Contract (`base.py`)

| Member | Meaning |
|---|---|
| `name` | Registry key. Callers select backends only by this string. |
| `execute(request) -> ExecutionResult` | Blocking. Runs one request to completion. This is the only abstract method. |
| `cleanup(success=False)` | Releases resources owned by **this instance**. The default is a no-op. |

`ExecutionRequest` carries `agent_name`, `command` (complete argv), `cwd`, `timeout_seconds`,
`stdout_file`, `stderr_file`, and an open `metadata` mapping (today: `{"phase": ...}`).

`ExecutionResult` carries `command`, `returncode`, `stdout`, `stderr`, `backend`, and an open
`runtime_metadata` mapping.

### Obligations of `execute`

- Return only after the run has finished. The backend runs any resume/send/poll steps internally.
- Write captured output to `stdout_file` / `stderr_file` and also return it in the result.
- Enforce `request.timeout_seconds` yourself. On expiry, stop or interrupt the work and raise
  `SprintRunnerError("FAILED_TIMEOUT", ...)`.
- Report other hosting failures as `SprintRunnerError` with a `FAILED_*` code. A non-zero worker
  exit is **not** an exception: return it in `returncode`.
- Raise `SprintRunnerError` from `agents.errors`, like the existing backends do. The runtime
  accepts that class and `runner.agents.errors.SprintRunnerError`; at runtime they are distinct
  classes.

### Cleanup ownership

Whoever obtains an instance from `BackendRegistry.get(...)` owns it and calls `cleanup()` once
when finished:

| Caller | Instance scope | Cleanup |
|---|---|---|
| `HermesSprintRunner` (`run-hermes-sprint.py`) | one per backend name per sprint (`_backend_cache`) | once, in `execute()`'s `finally`, `success=` sprint outcome |
| `HermesActorAdapter._execute_real_agent` (`runtime/hermes_adapter.py`) | one per task run | once, in `finally`, `success=` task outcome |

`cleanup()` must be idempotent and must release only what this instance created. Each `get()`
must return an instance the caller exclusively owns: the runtime runs tasks concurrently and
cleans up per task, so cleaning up a shared stateful instance would tear down another task's run.
If a backend pools expensive resources (for example a seat pool), the pool stays internal: each
instance is a lease, and `cleanup()` returns that lease. A factory may return a shared instance
only when that instance's `cleanup()` is a no-op, as in the test doubles.

### Timeouts and cancellation

- `request.timeout_seconds` is the authoritative bound, and the backend enforces it.
- `ExecutionManager` also wraps runtime tasks in `asyncio.wait_for`. Because the backend runs in
  `asyncio.to_thread`, an outer timeout or cancel **does not reach the backend**. The thread keeps
  running until the backend's own timeout fires, and then the `finally` cleanup runs. The contract
  has no out-of-band cancel. Add a generic one only when a backend concretely needs one.

### Runtime metadata

`runtime_metadata` is an open mapping. `HermesActorAdapter` reads these keys when they are present:
`verdict`, `summary`, `findings`, `repairable`, `trigger_replan`, `replan_reason`, `observations`,
`context_pressure`, `context_ratio`, and the usage fields normalized by `UsageSnapshotNormalizer`.
Backend-specific identifiers go here with a backend prefix (Herdr uses `herdr_workspace_id` and
`herdr_pane_id`). Never add backend-specific fields to `ExecutionRequest` or `ExecutionResult`.
The runtime copies the scalar entries (str/int/float/bool/None) to
`TaskExecutionResult.metadata["backend_runtime_metadata"]` and the backend name to
`metadata["execution_backend"]`, so IDs reach the task record without interpreting them.

## Selection

`registry.py` holds the one `default_backend_registry`. Callers resolve a name and call `get(name, **kwargs)`:

- sprint runner: phase `execution_backend` > `--backend` > spec `execution_backend` > `"subprocess"`
- runtime: task metadata `execution_backend` > `backend` > `"subprocess"`

Construction kwargs: `run_dir`, `sprint_id`, `logger` (and `keep_workspace` from the sprint
runner). Accept `**kwargs` so new kwargs do not break existing backends. Unknown names fail
closed with `FAILED_UNKNOWN_BACKEND`.

To add a backend, subclass `ExecutionBackend`, set `name`, and add one entry to
`default_backend_registry` (or inject a registry). No dispatch, scheduler, runtime or runner
logic changes are needed. Registration is explicit; there is no auto-discovery. `tests/test_backend_contract.py` proves this with a fake sessionful
backend.

## Future sessionful backend (not implemented)

A persistent runtime such as OpenRig fits behind this contract without changes. All of
the following stay **inside** the backend:

- allocating or resuming a session/seat, lazily on the first `execute`
- sending the prompt or command, polling status, and collecting the result into `stdout`/`returncode`
- interrupting on `timeout_seconds` and raising `FAILED_TIMEOUT`
- releasing the seat in `cleanup()` (or returning it to an internal pool)
- runtime-specific IDs in `runtime_metadata` under a backend prefix

Open points for that step, deliberately left out of the generic contract until a real need appears:

- The prompt reaches the backend only inside `command`. If a session runtime needs it
  separately, pass it through `request.metadata` (for example `metadata["prompt"]`) from
  `AgentAdapter.execute`. Do not add a new field.
- There is no out-of-band cancellation, as described above.
