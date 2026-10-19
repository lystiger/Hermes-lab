# Decisions

## D-001 — Step 2: execution-backend readiness for a future OpenRig backend (2026-10-12)

**Decision: PATH A — the existing `ExecutionBackend` contract is sufficient.** One narrow
integration fix is required in a caller. The contract itself does not change.

### Evidence (from repository, baseline `7d66c65`, full suite 366 passed / 6 skipped)

1. **Backend selection.** One registry, `runner/backends/registry.py:27`. Names are resolved in two places:
   - `runner/run-hermes-sprint.py:986`: phase `execution_backend` > CLI `--backend` > spec > `"subprocess"`.
   - `runtime/hermes_adapter.py:796`: task.metadata `execution_backend` > `backend` > `"subprocess"`.

   Neither path branches on provider or model names. `BackendRegistry.get` accepts any callable factory,
   and tests already register `lambda **kw: instance` (`test_phase11_0...:435`).
2. **Lifecycle assumptions.** Callers make one blocking call, `execute(request) -> ExecutionResult`, from
   `runner/agents/base.py:76`, which is the only call site. The sprint runner caches one instance per backend
   name and calls `cleanup(success=)` once, in `finally` (`run-hermes-sprint.py:994,2220`).
3. **One-shot semantics.** The request carries a complete argv and the result carries
   returncode/stdout/stderr. Nothing requires a fresh process: `HerdrBackend` already runs requests in a
   persistent workspace that it reuses across `execute` calls.
4. **Persistent resources inside a backend.** Yes. `HerdrBackend` keeps a workspace and panes, records them
   in `runtime.json`, and releases them in `cleanup()`.
5. **Runtime metadata in use.** `hermes_adapter.py:912` reads `runtime_metadata` keys verdict, summary,
   findings, repairable, trigger_replan, replan_reason, observations, context_pressure, context_ratio and
   usage fields. It is an open `Mapping`, so a new backend can add keys such as session or seat IDs
   without a contract change.
6. **Timeout, cancellation, cleanup.** The backend enforces `request.timeout_seconds` and raises
   `SprintRunnerError("FAILED_TIMEOUT")`. The contract has no cancel channel.
   `ExecutionManager` (`runtime/execution.py:233`) wraps the call in `asyncio.wait_for`, but the
   backend runs inside `asyncio.to_thread`, so an outer timeout or cancel never reaches it. The
   backend's own timeout still bounds the run. This gap already exists for subprocess and Herdr.

### What blocks a future OpenRig backend

- **Blocker (caller bug, not a contract gap):** `HermesAdapter._execute_real_agent`
  (`runtime/hermes_adapter.py:797`) creates a backend instance for every task and **never calls
  `cleanup()`**. Herdr hides this today because `keep_workspace` defaults to True. A seat-allocating
  backend would leak a seat on every task. Fix: call `backend.cleanup(success=...)` in a `finally`.
- **Not a blocker, document only:**
  - The prompt reaches the backend only inside argv. A sessionful backend that needs the raw prompt
    should receive it through `request.metadata` (an existing open Mapping), not a new field. That
    belongs to Step 3.
  - There is no out-of-band cancel. The run is bounded by `timeout_seconds`. Add a generic
    cancellation hook later only if Step 3 shows a concrete need.

### OpenRig fit

OpenRig can be added as one more `ExecutionBackend` implementation. Session/seat allocation, resume,
prompt/send, status polling, result collection and release all stay **inside** `OpenRigBackend`.
Each `registry.get(...)` instance is an owned handle. `cleanup()` releases that handle's resources
(for example, returns a seat to a pool). Any pool shared across handles stays internal to the backend.

### Latent issue found (out of scope, flagged)

`hermes_adapter.py:889` reads `getattr(raw_res, "exit_code", 0)`, but `ExecutionResult` defines
`returncode`, so the value is always 0. Nothing breaks today because `AgentAdapter.execute` raises on a
non-zero returncode before this line. The observation metadata is still misleading.

### Outcome (Codex review addressed)

- P2: shared-instance + per-task cleanup. Each `get()` must return an exclusively owned instance.
  A shared instance is allowed only when its `cleanup()` is a no-op. Pooling stays internal to the backend.
- P2: backend IDs were dropped. The runtime now copies scalar `runtime_metadata` entries to
  `TaskExecutionResult.metadata["backend_runtime_metadata"]`, plus `execution_backend`. This is additive.
- P3: registration is explicit: one entry in `default_backend_registry`. No dispatch logic changes.

## D-002: Step 3 OpenRig backend, blocked on local install (2026-10-12)

- Branch `step3/openrig-backend` created from `step2/backend-readiness` (`e44160c`).
- Discovery: `command -v rig` found nothing. No global npm package and no OpenRig files under ~, /usr/local or /opt.
- Status: **BLOCKED_REAL_OPENRIG_SMOKE_TEST**. The protocol decision (create, seat discovery, delivery,
  completion signal, JSON schemas) needs the installed CLI.
- Human decision: the human installs OpenRig. Opus does not install it or run `rig setup`.
  When it is on PATH, resume with read-only discovery: `--help` per subcommand, `rig doctor --json`, `rig ps --json`.

## D-003: Step 3 OpenRig discovery findings (2026-10-12, protocol not final)

Unblocks D-002: `rig` 0.6.9 (4b48ca21) is at ~/.local/share/mise/installs/node/26.7.0/bin/rig.
`rig doctor --json` reports healthy. Claude and Codex are installed and authenticated, tmux 3.7c passes,
and the daemon is on 127.0.0.1:7433. Warnings: Node 26 is untested (22/24 supported); cmux is absent (optional).
The user's `kernel` rig (4 seats) is running and must never be touched.

Verified CLI surfaces (JSON):
- `rig create <name> --runtime --cwd --json` returns {ok, rigId, rigName, pod, seat, node{logicalId,status,sessionName}}.
- `rig ps --nodes --json --rig <name> [--full]` returns a list of nodes, each with sessionStatus, startupStatus,
  lifecycleState, latestError and agentActivity{state, reason, evidenceSource, rawEvent, eventAt, stale, fallback, generation}.
- `rig transcript <session> --json --tail N` returns {session, lines, content, ingestHealth}.
  `rig capture <session> --json` returns {ok, sessionName, content}. Both are terminal text.
- `rig down <rigId> --delete --force --json` returns {rigId, sessionsKilled, deleted, errors[]}.
- `rig send` has --wait-for-idle and --verify. Per its help, --verify only proves the text appeared in the pane.

Completion primitive: agentActivity sourced from runtime hooks. ~/.openrig/reference/agent-state-taxonomy.md
lists Claude SessionStart/UserPromptSubmit/Stop hooks as "standing" (exactly-once turn boundaries). The Codex
hook rung is still "trial". Transcript quiescence and pane scraping are explicitly rejected as oracles.
So Step 3 supports **runtime claude-code only**.

Probe (rig hermes-probe-42f784ee, id 01M4Q7SJBB9CND1V87EKRMEFN3, cwd = scratch repo, torn down by id, kernel untouched):
- `rig create` launches the bundled **orchestrator** AgentSpec, which starts an autonomous turn
  (whoami, queue, ~/.openrig/workspace). That conflicts with the "OpenRig is not a scheduler" invariant,
  so Step 3 must use a Hermes-owned rig spec plus a minimal worker AgentSpec via `rig up <spec>`, not `rig create`.
- Under the team-default permissions (acceptEdits + allowances), the startup turn blocked within ~10s on a Bash
  permission prompt, reported as agentActivity {state: needs_input, reason: permission_prompt}. This is detectable,
  so the backend fails closed.

Open (human): the worker-seat permission posture. See the question in the session.

## D-004: Step 3 minimal OpenRig protocol (decided 2026-10-12, verified live with probe 2)

- **Version:** OpenRig 0.6.9. The backend accepts `0.6.x` only and fails closed otherwise (FAILED_OPENRIG_UNAVAILABLE).
- **Runtime:** claude-code only, used for Hermes agent `claude`. Any other agent fails with FAILED_OPENRIG_UNSUPPORTED_RUNTIME.
- **Ownership:** each execute() creates one ephemeral rig, named `hermes-<sanitized sprint>-<8 random hex>`.
  The backend records the exact `rigId` returned by `rig up`. A `rig ps` row counts as ours only if its rigId matches.
  Teardown always uses `rig down <rigId> --delete --force --json`, by id and never by name. No pooling.
- **Creation:** a Hermes-written rig spec plus a minimal AgentSpec (no persona, plugins or skills) is passed to
  `rig up <spec> --json`. `rig create` is not used because it launches the orchestrator persona.
  The seat cwd is a Hermes scratch dir under run_dir, **never the worktree**: OpenRig projects about 70 files into the cwd.
- **Permissions (human: mirror Hermes dontAsk):** launch posture floor (acceptEdits). The settings fragment allows
  Bash/Edit/Write/Read, denies Hermes's CLAUDE_GIT_MUTATION_DENIALS, and sets additionalDirectories=[task worktree].
  OpenRig overrides defaultMode, so an unlisted tool prompts instead of being denied. A prompt shows up as needs_input
  and the backend fails closed.
- **Seat ready:** startupStatus=ready and hook-sourced idle/Stop (evidenceSource=runtime_hook, not stale, not fallback).
  OpenRig still runs a short startup turn, which is why the backend waits for this.
- **Prompt transport:** generic `ExecutionRequest.metadata["prompt"]`, set by AgentAdapter. The backend appends a short
  Hermes result protocol (worktree path, nonce). Sent with `rig send --wait-for-idle N --json -- <session> <text>`,
  and `ok`+`sent` are required. The prompt is never logged.
- **Completion (delivery is not completion):** after the send, the backend needs a hook `Stop` with eventAt later than
  the send time, with the same generation, plus the nonce result file `<seat>/hermes-result-<nonce>.json` =
  {status: succeeded|failed, summary}. A hook UserPromptSubmit after the send is recorded as turn-started evidence.
  Non-hook samples (terminal_activity) are ignored.
- **Output:** stdout is a claude-result-shaped envelope built from the verified result file
  (type=result, subtype success/error, is_error, result=summary). This is backend-local runtime mapping.
  stderr is empty on success and the summary on failure. A transcript tail is saved to run_dir for diagnostics.
- **Timeout:** one monotonic deadline from request.timeout_seconds covers preflight→result. Every rig call gets the
  remaining time and polling is bounded. Expiry raises FAILED_TIMEOUT. Teardown has its own small budget.
- **Cleanup:** execute() releases its rig in `finally`. cleanup() retries any rig still owned and is idempotent
  ("No rig found" after our own down counts as released).
- **Codes:** FAILED_OPENRIG_EXECUTABLE_MISSING, _UNAVAILABLE, _UNSUPPORTED_RUNTIME, _CREATE, _SEAT_NOT_READY, _DELIVERY,
  _NEEDS_INPUT, _SESSION_LOST, _PROTOCOL, and the generic FAILED_TIMEOUT.
- **runtime_metadata:** openrig_version, openrig_rig_id, openrig_rig_name, openrig_session_name, openrig_node_id,
  openrig_runtime, openrig_generation, openrig_turn_started.

### D-004 outcome (2026-10-12)

- Implemented in `runner/backends/openrig_backend.py`, registered as `openrig`. `AgentAdapter` now passes
  `metadata["prompt"]`.
- Codex review 1 (4×P2, 1×P3), all fixed: the completion fence uses send_started/send_confirmed, the
  generation is required, a lost `rig up` response is reconciled, an unreleasable rig fails the task, and
  decode errors map to PROTOCOL.
- Codex verification review (4×P2), all fixed and covered by tests, with no third review per the brief:
  orphan adoption is limited to rigs new since the pre-launch snapshot, it retries 3 times within one
  20 s budget, and OSError maps to UNAVAILABLE.
- Live smoke ×3 through HermesActorAdapter → ClaudeAdapter → OpenRigBackend → a real claude-code seat:
  PASS each time. The commits contain only proof.txt, the rigs were released by id, and kernel, tmux and Herdr
  were unchanged.

## D-005: Step 4 problem 1, warm seat reuse with fresh context, pooled per job (2026-10-12)

Human decisions: a warm seat with fresh context for every task; seats are shared only within one Hermes job.

Evidence (probes 3 and 4, both torn down by id, kernel untouched):
- `/clear` is **not usable**. Claude starts a new native session, the OpenRig identity verdict becomes `mismatch`
  (process_identity_ambiguous), startupStatus becomes `attention_required`, and hook evidence drops to pane heuristics.
- `rig seat launch <session> --fresh --stop --reason .. --json` is OpenRig's supported, audited primitive. It returns
  {ok, seat{rigId,rigName,logicalId,nodeId}, status, sessionName, generation, supersededSessionIds}.
  The new occupant has a new generation, identity `verified`, hook evidence present, and no memory of the previous task.
- Timing to hook-idle: a new rig takes 27.8 s (the command itself 3.9 s); a fresh occupant takes 15.6 s (the command 2.0 s).
  Every launch has a startup turn (session identity + culture). It can't be removed without a global config change.

Design:
- A process-wide seat pool inside openrig_backend, keyed by job (sprint_id). Seats are leased exclusively under a lock.
- Reuse a seat only if its granted directory (the parent of the first task's worktree) contains the new task's worktree.
  Otherwise launch a new rig.
- A reused seat always gets `rig seat launch --fresh --stop` before the send. Ready means a hook Stop carrying the **new**
  generation. A newly created seat is already fresh.
- A seat goes back to the pool only after a clean protocol completion (a valid result file, whether the task succeeded or
  failed). Any exception (timeout, needs_input, session lost, protocol) releases the rig by its exact rigId.
- An idle seat is released after 120 s, and every pooled rig is released when the process exits. There's no job-end
  signal yet, so idle expiry is the job boundary in practice.
- Ownership is unchanged: exact rigIds only, and teardown is by id.

### D-005 outcome (2026-10-12)

- Implemented in `runner/backends/openrig_backend.py` (`_SeatPool`, `_Seat`, `_fresh_occupant`, `_new_seat`).
- Tests: 57 OpenRig tests (11 new reuse tests). Full suite 436 passed / 6 skipped. compileall OK.
- Live: T1 launched a rig in 34.0 s; T2 reused it with a new generation in 32.0 s. two.txt=NONE shows fresh
  context. Each commit has one file, the pool drain released the rig, and kernel, tmux and Herdr were unchanged.
- Not yet reviewed by Codex.

### D-005 Codex review (2026-10-14)

Five P2 findings, all confirmed and fixed in `openrig_backend.py`, each with a regression test:
1. A reused seat stayed in `pooled_rig_ids`, so a cached backend leaked it on failure. Now it is owned again on lease.
2. A timer callback that had already started could expire a later idle period. Callbacks are now fenced by a per-put token.
3. A failed expiry/drain teardown dropped the rigId. It is now kept in `_failed`, and drain() retries it.
4. A fresh relaunch accepted the old generation. `_Seat.generation` is now stored, and an equal generation is rejected.
5. Exit drain didn't wait for a teardown running on a timer thread. drain() now waits (up to RELEASE_TIMEOUT_SECONDS).
Second Codex pass found two more P2s, both fixed:
6. put() published the seat before timer.start(). If the start failed, the released seat stayed leasable. It now rolls back.
7. drain() ignored a wait timeout and returned while a teardown was still running. It now re-issues that teardown by id.
Tests: 64 OpenRig tests (both new ones fail on the old code). Full suite 444 passed / 5 skipped. compileall OK.
Live smoke (2026-10-14): both tasks rc=0 on one rig. T2 reused=True with a new generation. one.txt=SECRET-PAPAYA, two.txt=NONE (fresh context). The rig was released, 0 rigs were left, and kernel was untouched.

## D-006: Step 4 problem 2, OpenRig rigs must not outlive their job (2026-10-14)

Decision: (a) a finished sprint releases its job's idle seats at once, via `release_job`. (b) Every rig the backend
launches is recorded in a per-user ownership ledger. The next backend preflight releases the rigs of dead Hermes
processes. Ownership stays exact rigId only, as in D-004 and D-005.

- **Job end is the sprint runner's `finally`**, keyed by `sprint_id`, the key `_get_backend` uses. It is not the
  adapter's per-task `cleanup`. That runs after every task, so calling `release_job` there would tear the pool down
  after task one and undo D-005.
- **Contract:** one additive hook, `ExecutionBackend.release_job(job)`, with a no-op default. The sprint runner calls
  it on each cached backend. Idempotent. Leased seats are never touched. A failed teardown is kept and retried by
  the next `release_job` or by drain.
- **Ledger:** `runner/backends/openrig_ledger.py`. Location is `HERMES_OPENRIG_LEDGER_DIR`, then
  `$XDG_STATE_HOME/hermes/openrig-ledger`, then `~/.local/state/hermes/openrig-ledger`. The state dir is per user, not
  the run dir, so a crash in one run can be reconciled by the next. One file per process: `<host>-<pid>-<start>.json`.
  Liveness is pid present, not a zombie, and `/proc` start time unchanged. An uninspectable owner counts as alive.
  Entries from another host are never judged dead.
- **Order:** a rigId is recorded right after `rig up` returns it, and before anything relies on it. It is dropped only
  after `rig down` confirms. A ledger write failure fails the task closed and releases the new rig.
- **Reconcile:** runs in every preflight, within a shared 20 s budget. A failed release stays in the ledger and never
  fails the current task. A corrupt file is logged and kept.

Tests: 17 new in the fake-CLI suite. Five cover pool `release_job` (double call, unknown job, other jobs and leased
seats untouched, late expiry, retry after failure). Ten cover the ledger: survives a crash and is reconciled, live owner
skipped, reused pid treated as dead, non-ledger and kernel rigs never released, failed reconcile kept for retry, write
failure fails closed, foreign host skipped, corrupt file kept. Two cover the sprint runner's job-end call. Full suite
461 passed / 5 skipped. compileall OK.

Not verified live: per the hard rules no state-changing `rig` command was run, so the real `rig up`/`rig down` path
under reconcile is untested. The fake CLI covers the protocol only.

Known gaps (documented in the README): a crash inside the `rig up` call, before its response is parsed, leaves a rig
outside the ledger. The in-process `job_launcher` / `HermesActorAdapter` path, keyed by `job_id`, has no job-end hook
yet, so it relies on the 120 s idle timer.

## D-007: Step 4 problem 3, out-of-band cancel and exit-code fix (2026-10-14)

**Decision: cancel is an optional `cancel_event` on `OpenRigBackend`, set by the runtime when the task is
cancelled. The `ExecutionBackend` contract and `ExecutionRequest` do not change.** This revisits the D-001 note
"add a generic hook only if Step 3 shows a need": Step 4 shows one.

### Evidence (branch `step4/cancel`, baseline `cf0f367`, suite 444 passed / 5 skipped)

1. **How Hermes cancels today.** Only asyncio cancellation. `engine.request_cancel` and `ExecutionManager`'s
   `wait_for` cancel the coroutine, and the coroutine awaits `asyncio.to_thread`, so the backend thread never sees
   it. `runner/` has no cancel source at all.
2. **Wire.** `HermesActorAdapter.execute_task` creates one `threading.Event` per task, passes it to the backend
   factory as `cancel_event=`, and sets it on `asyncio.CancelledError`. Backends that do not take it ignore it,
   because every constructor accepts `**kwargs`.
3. **Checks.** At lease, at the top of each ready-wait and completion-wait poll, and before the prompt is sent.
   A set event raises `FAILED_OPENRIG_CANCELLED`. The existing `finally` releases the owned rig by exact `rigId`.
   A cancelled seat is never `put()` into the pool.
4. **Post-completion no-op.** Once `_wait_for_completion` has returned, the result is proven. No check runs after
   that, so a late cancel returns the success and pools the seat as usual.
5. **Exit-code bug.** `hermes_adapter.py` read `getattr(raw_res, "exit_code", 0)`, but `ExecutionResult` has
   `returncode`. Fixed to `returncode`, keeping the default 0. In production `AgentAdapter.execute` raises on a
   non-zero returncode before this line, so the bug was latent. The regression test uses a bare stub that returns
   `returncode=1`. It failed before the fix (`succeeded`) and passes now.

### Tests

- 7 new: cancel before launch; during ready-wait (one poll, then release by id); during completion-wait (never
  pooled); after completion (no-op); reused seat (released by id, pool empty); the real adapter path (cancelling the
  task releases the parked seat, one poll only); the exit-code regression.
- The adapter test is discriminating. Removing `cancel_event.set()` makes it fail, because without the cancel the
  fake clock runs the wait to its 120 s timeout (about 60 polls).
- Full suite 451 passed / 5 skipped. compileall of `runner` and `runtime` OK.

### Limits (documented in `runner/backends/README.md`)

- The sprint runner has no cancel source. Its runs still stop only at their timeout.
- A cancel during an in-flight `rig up` or `rig send` is honored when that call returns, up to 30 s for send.
  Killing the subprocess is not done.
- `test_runtime_infrastructure_wiring.py` mocks still set `exit_code = 0` and no `returncode`. They pass through the
  default 0. Converting them to `returncode` is a follow-up.
- No live smoke test in this step. No `rig` state-changing command was run, per the brief.

## D-008: Full-branch Codex review of step3/openrig-backend (2026-10-14)

Five findings, all confirmed and fixed with regression tests. Each test fails when its fix is turned off.
- P1: ledger values reached `rig down`, which also resolves names. A dead owner's ledger with "kernel" would have
  torn down the kernel rig. Now only 26-char ULID rigIds are accepted: by the ledger (read and record) and by `_release`.
- P2: `forget()` rewrote other processes' files under an in-process lock only, so a live owner could lose a new rigId.
  Ledger reads and writes now hold `flock` on `<dir>/.lock`.
- P2: a cancel set during the final completion poll still pooled the seat. Cancel is now re-checked before accepting a Stop.
- P2: put() published the seat before timer.start(), so another task could lease it and then have it torn down.
  The seat is now published only after the timer starts. If the timer already fired, the seat is torn down at once.
- P2: status polls got the whole remaining task time, so a hung daemon hid a cancel for minutes. Each `ps --nodes`
  poll is now capped at POLL_QUERY_SECONDS=10. A timed-out poll is retried, and the cancel check runs in between.
- Also closed the deferred job-end gap on the runtime path: `ReactiveJobEngine.run_until_complete` calls
  `ActorAdapter.release_job(job_id)` once the job is terminal. `HermesActorAdapter` tracks the backends used per job.
Tests: 478 passed / 5 skipped. compileall OK. Test rig IDs were converted to valid ULIDs.

### D-008 merge-gate re-review (2026-10-14): BLOCK → fixed

- P1: `rig down <id>` falls back to a *name* match when no rig has that id (OpenRig CLI resolveRigHandle;
  the daemon's /api/down itself is id-only). `_release` now checks first with `rig ps --json --include-archived`
  that the id still exists. An id that is gone counts as released and is never passed to `rig down`.
- P2: a cancelled worker thread could return its seat after the job-end release. The pool now remembers closed
  jobs, and put() for a closed job tears the seat down instead of pooling it.
- P2: the adapter dropped its job's backend names before teardown, so a failed release could not be retried.
  `OpenRigBackend.release_job` now raises while failures remain, and the adapter keeps the name until a release succeeds.
Tests: 482 passed / 5 skipped. Each new test fails when its fix is turned off.

### D-008 merge gate round 2 (2026-10-14): BLOCK → fixed

- P1: the existence pre-check was racy: a rig deleted between the check and `rig down` let the CLI fall back to a
  name match. Teardown now bypasses the CLI and posts to the daemon's id-only `POST /api/down`. 404 means already
  gone. Verified live: an unknown id returns 404 and nothing is touched. Tests isolate OPENRIG_HOME so they can never
  reach the real daemon.
- P2: a job closed while a seat's timer was starting could still get the seat pooled. Publication now re-checks closure under the lock.
- P2: the adapter dropped job retry state once the first release succeeded, so a late seat's failed teardown could
  not be retried. The adapter now keeps the names. Backend release_job is idempotent, so every call retries.
Tests: 485 passed / 5 skipped.

## D-009: Execution visibility contract, Hermes → LysControl (2026-10-14)

Human decisions: a new **Execution** page in LysControl; it covers **every backend** (subprocess, herdr, openrig), not only OpenRig.
LysControl ships as an Omarchy web app (http://localhost:3000, class `chrome-localhost__-Default`, workspace 5).
Phase A (Hermes) and Phase B (LysControl) are built in parallel against this contract. It is the source of truth.

### Events (persisted and streamed like every runtime event: GET /events, GET /events/stream)
`source_kind="runtime"`, `source_id=<backend name>`. job_id / task_id / run_id / actor_id are set when known.
`kind` is one of:
- `execution.started`: a backend began a task execution
- `execution.resource_acquired`: the backend has a resource (openrig: a seat, new or reused; herdr: a pane; subprocess: a process)
- `execution.resource_ready`: the resource can take the prompt (openrig: hook-idle on the new generation)
- `execution.running`: the prompt/command was delivered and the work is in progress
- `execution.finished`: clean completion (task succeeded or failed by the agent's own verdict)
- `execution.failed`: backend/protocol failure (metadata.errorCode = the SprintRunnerError code)
- `execution.cancelled`: stopped out of band
- `execution.resource_pooled`: openrig: the seat went back to the job pool (idle; metadata.expiresAt)
- `execution.resource_released`: the resource was torn down / freed
- `execution.release_failed`: teardown failed and is kept for retry

`metadata` (camelCase, every field optional except backend and executionId):
```
{ backend: "openrig"|"herdr"|"subprocess"|<other>,
  executionId: "<stable id for this task execution>",
  resource: { kind: "seat"|"pane"|"process", id: "<rigId|paneId|pid>", label: "<human label>" },
  reused: bool, generation: str, rigId: str, sessionName: str, nodeId: str,
  expiresAt: ISO8601, errorCode: str, error: str, durationMs: int }
```

### Snapshot: GET /execution
```
{ backends: [ { name, available: bool, detail: str } ],
  resources: [ { backend, kind, id, label, state: "acquiring"|"ready"|"running"|"idle"|"releasing"|"failed",
                 jobId, taskId, executionId, since: ISO8601, expiresAt: ISO8601|null, details: {} } ],
  openrig: { daemon: "up"|"down"|"unknown", ledger: { owners: int, rigIds: [str] } } | null }
```
The snapshot is the initial state. Events after it are applied on top. In-process state only; it never calls `rig` mutating commands.

## D-010: Phase A of D-009, Hermes emits execution visibility for every backend (2026-10-14)

Built against the D-009 contract, unchanged in shape. The clarifications below fill cases the contract did not
spell out. Human review is requested for them.

### What was built

- **Sink.** `ExecutionBackend` takes an optional `event_sink` constructor kwarg (default: no-op). `runner/backends/events.py`
  holds the event kinds, `execution_metadata()` (D-009 camelCase keys), `send_execution_event()` (never raises) and
  `ExecutionTrace`, which gives each execution a stable `executionId`, carries bound context, and emits terminal events once.
- **Adapter wiring.** `HermesActorAdapter(event_bridge=)` passes its sink to every backend it creates. The sink updates an
  in-process registry at once, then queues the event for one drain coroutine on the loop captured in `execute_task`.
  The drain calls `RuntimeEventBridge.persist_and_publish(source_kind="runtime", source_id=<backend>)` in order.
  Workers never wait on the store. A store error drops only that event. `job_launcher` passes the bridge in all three
  adapter constructions, including the resume path (`engine.event_bridge`).
- **Per backend.** Subprocess, Herdr and OpenRig emit the full lifecycle. OpenRig adds `acquired` (`reused`, `rigId`,
  `sessionName`, `generation`), `ready` (`generation`, `nodeId`), `pooled` (`expiresAt`), `released` and `release_failed`.
  Pool-timer expiry, `release_job()` and `drain()` emit through the seat (`_Seat.event`), so they keep the context of the
  last execution that held the seat. Ledger reconcile and cleanup retries release under their own `release:<rigId>` stream.
- **Registry and snapshot.** `runner/backends/execution_registry.py` holds `ExecutionRegistry` (keyed by
  `(backend, kind, id)`, thread-safe) and `build_execution_snapshot()`. `GET /execution` in `main.py` returns the snapshot.
  The snapshot runs only `rig ps --json` (daemon up or down), never a mutating command. `openrig.ledger` comes from the new
  `OwnershipLedger.summary()`, which takes no lock, creates no directory and deletes nothing. `stale_owners()` is not used.

### Contract clarifications (the human decides whether to keep them)

1. **Subprocess `resource.id` = `executionId`, not a pid.** `subprocess.run` does not expose the child's pid. Tracking the pid
   would mean switching to `Popen`, which changes how the process is spawned. The label is the agent name.
2. **Herdr `resource_released` = the pane is freed.** It fires when the worker command finishes. The pane stays in the
   workspace when `keep_workspace` is set. The registry drops the row.
3. **Orphan releases get `executionId = "release:<rigId>"`.** This covers ledger reconcile and `cleanup()` retries of a rig
   that no task holds.
4. **`task_id` is set by the adapter (reviewer fix).** Backends do not know the runtime task, so `HermesActorAdapter` gives
   each task's backend a sink that stamps `task_id`, `run_id` and `actor_id` on its events and registry rows. A pooled seat's
   later events (expiry, release) keep the ids of the last task that held it.
5. **Failures precede releases.** Within one execution the terminal event (`failed`/`cancelled`) is recorded before its
   `resource_released`, so the stream reads in causal order.
6. **Resource states in the snapshot.** `acquiring` after `acquired`, `ready`, `running`, `releasing` after `failed` or
   `cancelled`, `idle` after `pooled`, `failed` after `release_failed`. `released` removes the row. `finished` leaves the state unchanged.
7. **`openrig` is `null` when `rig` is not on PATH.** A backend's `available` is true only when the daemon is up.

### Scope and limits

- **The sprint runner (`run-hermes-sprint.py`) emits nothing.** It builds backends without an adapter or bridge. Its runs are
  not visible on `/execution`. Wiring it would mean giving the sprint runner a sink, which is a separate step.
- Events are persisted only while the adapter's loop runs. The `atexit` drain of the default seat pool reaches the registry
  but not the store.
- The registry is per process. After a restart, only the OpenRig ledger summary shows rigs left behind.

### Verification

- Full suite **518 passed / 5 skipped** (baseline 485 / 5, plus 33 new in `tests/test_execution_events.py`). `compileall runner runtime` OK.
- New tests cover: event order per backend (subprocess success, nonzero exit, timeout, missing executable; herdr success,
  command failure, failure before a pane; openrig success, reuse, failed send, cancel before lease, pool expiry, `release_job`,
  `drain`, failed release then retry, end to end through the adapter into the bridge); the D-009 metadata contract (known kinds,
  allowed keys only); sink safety (sink errors never fail a task, a slow store never blocks a worker, a failing store drops
  only its event, concurrent emits from 8 threads persist in per-thread order); registry transitions; snapshot shape; the
  snapshot's read-only guarantee (only `rig ps --json`, no ledger directory created); the `/execution` route.
- **Mutation checks**, each caught by a test, then reverted: failure emitted after release (order test fails); blocking
  sink (never-blocks test fails); sink errors escaping (sink-errors test fails).
- **Live, read-only:** `build_execution_snapshot()` against the real daemon returned `daemon: up`, parsed correctly, and an empty
  ledger. No `rig` state-changing command ran, the `kernel` rig was not touched, and `/api/down` was not called.
  No live OpenRig task was run, since that needs a state-changing `rig up`.

### Follow-ups

- Decide whether the sprint runner should get a sink (scope item above).
- Add `taskId` (clarification 4) if LysControl needs to group by task.

### D-010 addendum: snapshot cutoff (merge-gate round 2)

`GET /execution` also returns `takenAt` (epoch seconds, the same clock as event `rawTs`), read before the resources.
Clients ignore execution events with `rawTs <= takenAt`, because the snapshot already reflects them. This matters
because execution events are persisted best-effort: replaying older history must never bring back a resource that
the snapshot shows as gone.

## D-011: Replanned work keeps its execution path (2026-10-14)

Found live (D-009 Execution page): a Claude/OpenRig verifier task failed, and its fallback `fix_*` tasks ran on Antigravity
via subprocess with no role guard. A "diagnostic" fallback then passed, and the job reported COMPLETED.
Fixed on fix/repair-task-routing. Four Codex rounds; MERGE OK with full agreement:
- Task-failure fallbacks inherit `assigned_actor` and execution metadata (backend, role, prompt, limits, options). They get
  a fresh worktree, branch and history. They keep the original description, so success means the work was done, and
  carry `fallback_errors` (accumulated across chains) into the prompt. They see observations from their whole lineage,
  and never invent capabilities the source task did not declare.
- Verification repairs tied to a task (`obs.task_id`) inherit its actor, backend and lineage, use the source task's
  capabilities, run with role=builder, and keep their own repair instructions (no inherited prompt file).
- Deadlocks on failed/blocked/cancelled prerequisites are reported as unrecoverable (the job blocks), instead of adding
  an unblock task that could never clear them.
Agreed limits: unlinked/general repairs and discovery work stay capability-routed on the default backend, because the
sprint-level execution_backend does not reach them. Verifier fallbacks keep the no-mutation guard.

## D-012: Runner visibility, sprint-level backend, cancel during send (2026-10-14)

- **Sprint runner → Execution page.** `run-hermes-sprint.py` gives its backends a sink that posts `execution.*` to
  `/internal/events`, with `taskId` set to the running phase and `actorId` to its agent. The API publishes runtime ids
  on the bus and applies execution events to the registry, so `GET /execution` shows runner-owned resources.
- **Sprint-level backend.** Job-level work (general repairs, discovery, unblocking) has no backend of its own. It now
  uses the sprint's `execution_backend` when that backend supports the actor the scheduler chose (`supports_agent`;
  OpenRig: claude only), else subprocess. An explicit task backend is never second-guessed.
- **Cancel during `rig send`.** In production, send runs via Popen, polls the cancel event every 0.5 s, and is killed on
  cancel (FAILED_OPENRIG_CANCELLED; the rig is then released by id). `rig up` remains uninterruptible.

## D-013: Persisted Execution page and interruptible rig up (2026-10-14)

- **Persistence.** The API server enables `ExecutionRegistry` persistence at startup (`$HERMES_EXECUTION_STATE`, default
  `~/.local/state/hermes/execution-registry.json`). It writes atomically after every change, with snapshot and write under
  one lock. Reloaded rows are flagged `details.restored` and are not trusted: restored OpenRig rows whose rig the daemon no
  longer lists are pruned at snapshot time (only when the daemon answered), any restored row unrefreshed for 30 min is
  dropped, and the next live event clears the flag. The sprint runner and tests never persist.
- **Interruptible `rig up`.** It uses the same Popen/cancel path as `rig send`. On cancel it is killed, and orphan
  recovery adopts whatever it already created by exact rigId and releases it.

### D-013 round 2 (Codex BLOCK, 3 x P2, all accepted)

- **Late rigs from cancelled or lost launches.** Before `rig up`, the launch is recorded by its unique Hermes name in
  `<ledger>/<owner>.pending` (state `launching`). It is cleared when its rigId is tracked, otherwise marked `abandoned`.
  Every preflight reconciles abandoned launches, and launches whose owner died: a rig with exactly that name in the
  `rig ps` listing is released by its rigId. A launch still in progress in a live process is never touched. Entries
  are dropped after 1 h. If the pending record cannot be written, the launch does not start.
- **Saves are off the execution path.** `apply()` only schedules a save. One background thread writes, coalescing
  bursts.
- **Restarts no longer renew stale rows.** `restoredAt` is kept across restarts, and TTL expiry is persisted.
- Round 3 fixes: the pending launch record is cleared only after the rigId is *durably* written to the ledger, so a
  failed ownership write followed by a failed teardown still leaves a recovery handle. The registry `flush()` waits for
  queued writes and for a write already in progress, within one timeout. The API flushes the registry at shutdown.

## D-014: API surface follow-ups from the LysControl audit (2026-10-14)

- `GET /jobs/recoverable` was shadowed by `/jobs/{job_id}`, and crashed once it was reachable. Both are fixed.
- CORS is an explicit allowlist (LysControl on 3000, preview on 3001, Vite on 5173), overridable with `HERMES_CORS_ORIGINS`.
  It is not "any local port", because Hermes has no authentication.
- **Open follow-up (security):** control endpoints (`POST /jobs`, `/messages`, `/jobs/{id}/cancel|resume`,
  `/internal/*`) are unauthenticated, and bodyless POSTs are reachable cross-site as simple requests (CSRF), whatever
  the CORS setting. Needs a local auth token or a CSRF guard before Hermes is exposed beyond a single-user machine.

## D-016: A/B test, Herdr vs OpenRig as Hermes' Claude backend (decided 2026-10-15, before running)

Why: OpenRig is the most complex part of Hermes (backend, ledger, pending launches, ID-only teardown; ~1,550 lines
vs 376 for Herdr), only runs claude-code, and its seats are invisible in the Herdr cockpit. The user has never used
OpenRig outside this project. Question: does it earn that complexity?

Design (fixed before any run):
- Same sprint spec, same scratch repo with real tests and verification_steps, 4 builder tasks, Claude only (the only
  runtime both backends support). 3 runs per arm, alternating H, O, H, O, H, O.
- Model: Haiku 5.5 in both arms. Herdr passes `--model claude-haiku-5-5`; OpenRig cannot pass a model yet (H5), so the
  OpenRig daemon is started with ANTHROPIC_MODEL=claude-haiku-5-5. The model actually used is checked per task from
  the run output; a run whose model differs is invalid and re-run.
- Measured per task from execution events and run summaries: success, wall time, startup overhead
  (resource_acquired -> running), completion errors (false done / missed done), leftovers after the run (rigs, panes,
  processes), context isolation. Subjective: the user watches one run per arm (Herdr cockpit vs `rig tui` / `rig ui`)
  and rates how easy it is to follow.

Decision rule (pre-registered):
- OpenRig stays a Hermes backend only if it is clearly more reliable (fewer failed or mis-detected tasks), or more than
  20% faster per sprint, with cleanup no worse than Herdr.
- Otherwise Herdr becomes the default backend for every role, OpenRig becomes optional and unused by default, and H5
  (passing models into OpenRig seats) is dropped.
- Run log: herdr-1 invalid (setup bug, not backend): the seed repo had no .gitignore, so __pycache__ got committed and
  Claude tried `git checkout`, a denied git mutation that fails the Herdr path fast. Fixed for both arms: .gitignore in the
  seed, and every prompt says "Do not run any git commands; Hermes commits your changes for you." Runs restart at herdr-1.
- Run log: herdr-1 (second attempt) invalid (harness, not backend): the spec used `verification_steps` but the runner
  reads `verification`, so the runner's pytest-less venv step ran and failed. The integrated code passed all 9 tests
  when checked manually. Fixed the key for both arms, and the harness now runs the tests itself after every run (same
  independent verdict for both arms). Runs restart at herdr-1 again.
- **Result (2026-10-15):** 6 valid runs, all Haiku 5.5 (379/379 logged messages). Herdr: 3/3 READY_FOR_REVIEW, 3/3
  independent tests pass, 0 completion errors, no leftovers, sprint 62.0 / 61.8 / 68.5 s (mean 64.1 s). OpenRig: 3/3,
  3/3, 0 errors, no leftovers (rig released each time), sprint 158.3 / 162.4 / 149.3 s (mean 156.7 s). OpenRig is ~2.4x
  slower, a fixed ~20-25 s per task from the seat lifecycle (new rig, then fresh-context relaunch per reuse).
- **Decision (per the pre-registered rule):** OpenRig is neither more reliable nor faster, so **Herdr is the default
  backend for every role; OpenRig stays as an optional backend, unused by default; H5 is dropped.** Limits: n=3 per arm,
  short tasks; hung or interactive sessions (where hook-based completion could matter) were not tested. Revisit only if a
  real failure shows Herdr's exit-code completion is insufficient.

## D-017: LysStack as a company; four core employees; portraits with state-driven expressions (2026-10-15)

Decided with the user before implementation.
- **LysStack is the company.** Hermes, Claude, Codex and Gemini are its **four core employees**: personas with character
  sheets, art and a voice. Other providers/runtimes or models with no character are **staff without a card**: a neutral
  badge (name, runtime, role), never invented lore. A model is an employee's working mode, not a new person
  ("Claude (Haiku 5.5) as Scaffolder").
- **Cards are not regenerated.** Each sheet's affiliation (The Collective, The Eternal Library, The Starlit Network,
  LYS Stack) is recorded as that employee's department/home team inside LysStack; the persona's company is LysStack.
  Optional polish only: fix "Attalysis" and change Codex "Execute" to "Verify" on the Hermes card.
- **UI shows a portrait with state-driven expressions, not whole cards.** Each sheet's three Expressions tiles are
  extracted (never generated or AI-upscaled) and mapped to real Hermes state: idle -> calm/neutral, running -> focused,
  succeeded -> happy, failed/blocked -> surprised. 160 ms crossfade; instant swap under reduced motion. The full sheet is
  an optional "view character sheet" link. Expression tiles are small (~170 px): avatar use (96-128 px) only; the large
  dossier pane keeps the cutout portrait.
- **D-015 approved (2026-10-15):** Codex AGREE after revisions 2, 3, 3a and 3b (reviews in docs/design/agent-model-review-*.md).
  Implementation order per revision 3 item 13: contracts -> H1 personas -> H3 run/event persistence -> H4 readiness -> H2 /agents
  -> client migration -> remove legacy fields.

## D-018: Usability before experiments; then Hermes vs a single Herdr orchestrator (2026-10-15)

Decided with the user.
1. **LysControl usability milestone (M7) comes first,** on the current data model (the D-015 agent-model rebuild, M6,
   follows later). Done means, and is checked automatically where possible:
   - **No overlapping or clipped text** at 1280, 1440, 1920 px and a narrow 900 px window: an automated DOM check
     (overlapping text boxes, horizontal overflow, clipped text without a tooltip) runs on every page, plus screenshots.
   - **One consistent icon set** replacing ad-hoc glyphs and unorthodox symbols; every icon has an accessible label.
   - **Sidebar collapses and expands** (button + keyboard), remembers its state, auto-collapses on narrow windows.
   - **Smooth scrolling:** each page has one clear scroll container, no double scrollbars, no layout jumps on live
     updates; reduced motion respected.
   - **Real data sync:** pages update live from the event stream and the snapshot without manual refresh; a visible
     "last updated" and clear stale/disconnected states.
2. **Then an experiment, designed and recorded before running:** the same tasks done by (A) Hermes with its roles,
   routing, guards and harness, and (B) "pure Herdr with one orchestrator agent spawning workers", the way the user
   works today. Compare speed, task success, rework, operator effort and cost. Hypothesis to test, not assume:
   Hermes' overhead (rules, guards, harness) pays for itself in reliability.

## D-019: Herdr seat pool (2026-10-19)

Today the Herdr backend creates a new pane for every phase (splitting the root pane downward, `_create_worker_pane`)
and labels it with the phase name. In multi-phase jobs this yields stacked panes used only once. The operator wants
fixed, named seats instead: one Herdr workspace containing a set of named panes, where any agent can run in any
free seat, one agent at a time per seat, with one reserved "hot seat" for priority work.

### Decisions

1. **Workspace and Seats.** Seats are named panes inside the single runner workspace for the sprint/job.
   Seats are identified by stable labels: `seat-1` through `seat-N` for normal pool seats (e.g., `seat-1` … `seat-5`),
   and `hot` for the hot seat. Seats are created on first use if missing (or discovered from the workspace if already created).
2. **Assignment and Exclusive Leases.** Pool seats (`seat-1` … `seat-N`) are fungible and can be assigned to any agent.
   Each seat is acquired under an exclusive lease for the duration of a command and released back to the pool when the command ends.
3. **Queueing / Waiting.** When no eligible seat is free, callers wait until a seat is released or until
   `acquire_timeout_seconds` expires. If the timeout expires before a seat is acquired, execution fails with a clear
   `SprintRunnerError("FAILED_SEAT_TIMEOUT", ...)`.
4. **Hot Seat Rules.** The `hot` seat is reserved exclusively for phases configured with `"priority": "hot"`.
   Non-hot phases never acquire the hot seat. Hot phases only use the hot seat. The hot seat may run even when all
   normal pool seats are busy.
5. **No Preemption.** Running phases are never preempted. A hot phase waiting on an occupied hot seat will wait for
   the hot seat to be released.
6. **Execution Banner.** At the start of each run in a seat, a visible banner line is written to stdout/log before executing
   the worker command, displaying the job id, phase name, and persona/agent name:
   `=== [seat:<label>] job:<sprint_id> phase:<phase> agent:<agent_name> ===`.
7. **Survives Across Instances.** Seat pool and pane state survives across backend instances for a run using the backend's
   existing runtime state file (`runtime.json`).
8. **Resource Events (D-009).** When the seat pool is active, resource events (`execution.resource_acquired`, etc.) use
   the seat label (`seat-1`, `hot`, etc.) as the resource id and label so LysControl's Execution page reflects the seats.
9. **Configuration Shape and Default Off.** The seat pool is configured in the sprint spec or passed via backend settings:
   ```json
   "seat_pool": {"size": 5, "hot": true, "acquire_timeout_seconds": 600}
   ```
   When absent (default off), the backend behaves exactly as before (creating ad-hoc panes per phase).
10. **Follow-ups.** The long-lived sessionful hot seat (retaining agent session state across tasks) is out of scope here
    and tracked as a future follow-up.


## D-020: Model registry (2026-10-19)

### Decisions

1. **Hermes owns model choices.** Each registered agent has an allowlist and a configured default in
   `config/agent_models.json` (local, ignored); the example file ships safe fallback lists. Claude uses
   `sonnet`, `opus`, `haiku`; Codex adds the local CLI config model; agy discovers models with a 60 s cache.
2. **API.** `GET /agents/models` exposes configured default/effort, allowed models and lastUsed.
   `PUT /agents/{id}/model` validates against the server allowlist and atomically persists the setting.
   Browser model strings never reach a CLI without this validation.
3. **Phase boundary.** Changes apply to the next phase only. Explicit phase model options win over
   configured defaults; absent either, the CLI chooses. A running phase retains its resolved setting.
4. **Configured and used are distinct.** `/agents` shows the configured default (or null).
   `agent.started` records model, effort and source (`phase`, `config`, `cli-default`); lastUsed retains
   that run setting separately. A CLI-selected model remains null when its identity is unknown.
5. **Effort is part of the setting.** Codex reasoning effort and agy effort persist alongside the model;
   Codex receives `model_reasoning_effort`, agy receives `--effort`. Claude has no effort setting here.

### D-020a

Model descriptors add `models: [{id, label, efforts}]` while preserving `configured`, `allowed`,
and `lastUsed`. Efforts are validated per model. Codex reads the CLI models cache on every request
(including mtime changes), includes the CLI config model, and uses static low/medium/high fallbacks
when the cache is missing or invalid. Claude aliases remain available; reported full IDs persist in
ignored `config/agent_models.seen.json`.

agy groups low/medium/high CLI IDs into base models; launch encodes effort in the ID, choosing medium
or the first offered effort when unspecified. Existing full CLI IDs pass through. PUT normalizes them.
After execution, Claude modelUsage (largest input plus output token total), Codex header, or the agy
CLI ID records `source: reported`. Requested model/effort/source remain alongside the report;
`reportedModel` is included in runtime and completion/failure event metadata. Missing reports preserve
the resolved launch setting, including null with `cli-default`.
