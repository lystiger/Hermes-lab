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
              └── OpenRigBackend      "openrig"     one task on a Hermes-owned OpenRig seat, warm-pooled per job
```

## Contract (`base.py`)

| Member | Meaning |
|---|---|
| `name` | Registry key. Callers select backends only by this string. |
| `execute(request) -> ExecutionResult` | Blocking. Runs one request to completion. This is the only abstract method. |
| `cleanup(success=False)` | Releases resources owned by **this instance**. The default is a no-op. |
| `release_job(job)` | Called once by the sprint runner at job end. Releases resources pooled for `job`. Must be safe to repeat. The default is a no-op. |

`ExecutionRequest` carries `agent_name`, `command` (complete argv), `cwd`, `timeout_seconds`,
`stdout_file`, `stderr_file`, and an open `metadata` mapping (today: `{"phase": ..., "prompt": ...}`;
`prompt` is the agent's prompt for backends that deliver it directly instead of via argv; never log it).

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

## OpenRigBackend (`openrig_backend.py`)

A minimal proof that a sessionful runtime fits behind the contract. OpenRig owns only the seat:
its lifecycle, message delivery and terminal state. Hermes keeps job state, the DAG, scheduling,
worktrees and verification.

**Tested with:** OpenRig 0.6.9. The backend accepts `0.6.x` only.
**Supported:** Hermes agent `claude` on OpenRig runtime `claude-code`. Other agents fail with
`FAILED_OPENRIG_UNSUPPORTED_RUNTIME`. The Codex hook rung is still "trial" in OpenRig 0.6.9, so
Codex completion can't be proven yet.

**Prerequisites:** `rig` on PATH, the daemon running (`rig doctor --json` healthy), and Claude
authenticated. Hermes runs no setup and changes no global OpenRig or Claude settings.

**Select it:** set `execution_backend: openrig` on a phase or task, or pass `--backend openrig`.

### Lifecycle of one `execute()`

1. **Preflight.** Checks that `rig` exists, `rig --version` is 0.6.x, and `rig ps --json` answers (daemon up).
2. **Lease or launch.** First tries to lease an idle seat from the per-job pool (see "Seat reuse" below).
   Otherwise it writes a Hermes-owned rig spec and a minimal AgentSpec (no persona, skills or plugins)
   under `<run_dir>/openrig/<rig-name>/`, then runs `rig up <spec> --json`. The rig name is
   `hermes-<sprint>-<8 random hex>`, and the exact `rigId` returned is recorded as owned. The seat's cwd
   is `<rig-dir>/seat`, **not** the worktree, because OpenRig projects `.claude/`, `.mcp.json` and
   `.openrig/` into the cwd. The worktree's **parent** directory is granted through
   `permissions.additionalDirectories`, so sibling task worktrees of the same job can reuse the seat.
   The prompt still confines the agent to its own task worktree.
3. **Permissions.** The settings fragment allows Bash/Edit/Write/Read and denies Hermes's git-mutation
   patterns. OpenRig launches Claude in `acceptEdits`, so an unlisted tool prompts; the backend sees that
   as `needs_input` and fails closed.
4. **Ready.** Waits for `startupStatus=ready` and a hook-sourced idle `Stop`. OpenRig runs a short
   startup turn, and the backend never sends into it.
5. **Send.** `rig send --wait-for-idle N --json -- <session> <prompt + result protocol>`, requiring `ok` and `sent`.
6. **Completion.** Delivery is not completion. The backend requires a `runtime_hook` `Stop` event, not
   stale and not fallback, with `eventAt` later than the send and the same occupant `generation`. A hook
   `UserPromptSubmit` after the send is recorded as `openrig_turn_started`. Heuristic
   (`terminal_activity`) samples are ignored.
7. **Result.** The prompt asks the agent to write `<seat>/hermes-result-<nonce>.json` =
   `{"status": "succeeded"|"failed", "summary": ...}` last. A missing or malformed file fails closed.
   stdout is a claude-result-shaped envelope built from that file, so `ClaudeAdapter` validation runs
   unchanged. stderr is the summary on failure. A transcript tail is saved to `<rig-dir>/transcript.txt`.
8. **Return or release.** After a clean protocol completion (a valid result file, whether the task succeeded
   or failed) the seat goes back to the job's pool. Any exception releases it with
   `rig down <rigId> --delete --force --json` in `finally`. `cleanup()` retries any rig this lease still owns,
   never touches seats handed back to the pool, and is idempotent; "No rig found" after our own down counts
   as released.

### Seat reuse (warm seat, fresh context, per job)

- **Pool.** A process-wide pool inside `openrig_backend.py`, keyed by job (`sprint_id`). Each seat is leased
  to one task at a time, and seats are never shared across jobs.
- **Fit.** A pooled seat is reused only if the new task's worktree lies under the seat's granted root.
  Otherwise a new rig is launched.
- **Fresh context.** A reused seat always gets `rig seat launch <session> --fresh --stop --reason ..
  --json` before the send. That's OpenRig's supported, audited "blank new occupant", and it brings a new
  generation. The response must name our exact rigId and session. The seat counts as ready only when a hook
  `Stop` carries that **new** generation, so the old occupant's evidence never counts.
- **Why not `/clear`.** `/clear` starts a new native Claude session that OpenRig reports as an identity
  `mismatch` with `attention_required`, and hook evidence is lost.
- **Job end.** When a sprint finishes, the sprint runner calls `release_job(sprint_id)` on each cached
  backend, so the job's idle seats are torn down immediately. The call is idempotent: a repeat call, or a
  call for an unknown job, does nothing. Leased seats are not idle, so they are never touched.
  `HermesActorAdapter` does **not** call `release_job` after each task. That would tear the pool down
  after task one. See Known limitations for the in-process `job_launcher` path.
- **Expiry.** An idle seat is still released after 120 s, as a backstop. Every pooled seat is also released
  when the process exits (`atexit`).
- **Measured (OpenRig 0.6.9).** A fresh occupant reaches hook-idle in about 16 s, against about 28 s for
  a new rig. In a live two-task run the end-to-end times were 34 s (new rig) and 32 s (reused): the
  agent's own work time dominates and varies between tasks.

### Ownership ledger and crash recovery

Every `rigId` the backend launches is written to a ledger before anything relies on it. It is removed only
after `rig down` confirms the release. The ledger lives in `openrig_ledger.py`.

- **Location.** A per-user state dir, not the run dir: after a crash, the next run is a new run dir, and
  reconciliation must still find the old entry. Resolution order: `HERMES_OPENRIG_LEDGER_DIR`, then
  `$XDG_STATE_HOME/hermes/openrig-ledger`, then `~/.local/state/hermes/openrig-ledger`.
- **Layout.** One JSON file per owning process, `<host>-<pid>-<start>.json`, holding `{host, pid, started, rigIds}`.
  `started` is the process's `/proc` start time. Each process writes only its own file, and writes are atomic.
- **Reconcile.** Every preflight releases the rigIds of entries whose owner is provably gone on this host:
  the pid does not exist, the process is a zombie, or the pid was reused (the start time differs). An owner
  that cannot be inspected counts as alive, so nothing is released on a guess. Entries from other hosts are
  skipped. The reconcile budget is 20 s, shared across the pass, and never extends the task's own deadline.
- **Retry.** A failed reconcile release stays in the ledger and does not fail the current task. The next
  preflight retries it. A corrupt ledger file is logged and kept, never released.
- **Fail closed.** If the ledger cannot be written, the task fails with `FAILED_OPENRIG_UNAVAILABLE` and the
  new rig is released.
- **Exact ids only.** Reconcile releases only rigIds from the ledger, by id. It never matches names, and never
  touches `kernel`, the user's rigs, adopted sessions or Herdr.

The backend only ever stops rigs whose `rigId` it recorded. A `rig ps` row with a matching session name
but a different `rigId` fails closed. It never touches `kernel`, the user's rigs, adopted sessions or Herdr.

### Timeout

One monotonic deadline from `timeout_seconds` covers everything from preflight to the result. Each `rig`
call gets only the remaining time, polling is bounded, and expiry raises `FAILED_TIMEOUT`. Teardown has
its own 60-second budget. If `rig up`'s response is lost (timeout or garbled output), the backend spends
at most 20 more seconds (3 bounded `rig ps` checks) looking for a rig that carries its random name **and**
was absent from the pre-launch snapshot. It adopts that rig only by its exact `rigId`, then tears it down.

### Errors

`FAILED_OPENRIG_EXECUTABLE_MISSING`, `_UNAVAILABLE` (daemon, version or CLI failure),
`_UNSUPPORTED_RUNTIME`, `_CREATE`, `_SEAT_NOT_READY` (startup attention or a prompt during startup),
`_DELIVERY`, `_NEEDS_INPUT` (a prompt mid-task), `_SESSION_LOST` (seat gone or occupant changed),
`_PROTOCOL` (malformed JSON, ownership mismatch, missing generation, missing or invalid result file),
and `FAILED_TIMEOUT`. If an owned rig cannot be released, an otherwise successful task fails with
`FAILED_OPENRIG_UNAVAILABLE` naming the rig, and `cleanup()` retries it.

### runtime_metadata

`openrig_version`, `openrig_rig_id`, `openrig_rig_name`, `openrig_session_name`, `openrig_node_id`,
`openrig_runtime`, `openrig_generation`, `openrig_turn_started`. These are scalars, so the runtime copies
them into `TaskExecutionResult.metadata["backend_runtime_metadata"]`.

### Known limitations

- Seats are warm-pooled per job, but every task still gets a fresh occupant and pays its startup turn
  (~16 s). There's deliberately no conversation continuity across tasks.
- **Crash recovery is by ledger, not by discovery.** A crash releases its rigs at the next preflight, but only if
  the rigId was recorded. A crash **inside** the `rig up` call, before its response is parsed, can leave a rig
  that is not in the ledger. Nothing on the next run releases it, and a user has to remove it by hand. Its name is
  `hermes-*`, and that is never used to match it. The ledger is also per-user state: it is not shared across machines.
- **No job-end hook for the in-process `job_launcher` path.** Sprint runs release their seats at sprint end. The
  `HermesActorAdapter` path, keyed by `job_id`, has no job-end call yet, so its idle seats are released by the
  120 s idle timer or at process exit.
- The granted root is the worktree parent, so a seat can technically reach sibling worktrees of its job.
- No out-of-band cancel: a cancelled Hermes task stops at its own timeout, then the rig is released.
- The result file relies on the agent following the protocol. An agent that skips it fails closed.
- The backend is coupled to OpenRig 0.6.x JSON shapes (`up`, `ps --nodes --full`, `send`, `down`).
- The sprint runner reuses one backend instance per sprint. That's safe, because each `execute()` leases
  and returns or releases its own seat.
