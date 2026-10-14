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
