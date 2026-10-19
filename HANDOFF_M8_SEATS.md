# Handoff: Hermes M8 Phase 2 — Herdr Seat Pool (D-019)

## Overview
Hermes M8 Phase 2 implements fixed, named seat pooling for the Herdr execution backend.
Instead of splitting a new pane downward for every phase (which produced stacked panes used once),
a workspace can now host a fixed pool of named seats (`seat-1` … `seat-N`, plus an optional `hot` seat).
Panes are created on first use and reused across commands (`herdr pane run <pane_id> <command>`).
The feature is default-off, ensuring 100% backwards compatibility when `seat_pool` is not specified.

---

## Files Changed

1. **`.agent/DECISIONS.md`**
   - Recorded `## D-019: Herdr seat pool (2026-10-19)`.
   - Documented seat naming (`seat-1` … `seat-N`, `hot`), exclusive leasing, queueing with timeout,
     hot-seat rules, execution banner, persistence via `runtime.json`, D-009 resource events, and config shape.

2. **`runner/backends/herdr_backend.py`**
   - Added `Seat` and `SeatPool` classes.
   - `SeatPool`:
     - Ensures workspace and allocates panes by seat label on first use (`ensure_seat_pane`).
     - Leases/releases seats with exclusive lock and `threading.Condition`.
     - Implements queueing with `acquire_timeout_seconds` and raises `SprintRunnerError("FAILED_SEAT_TIMEOUT")` on timeout.
     - Implements hot seat priority rules: `hot` seat is reserved exclusively for phases with `"priority": "hot"`.
       Normal phases never acquire `hot`; hot phases only take `hot` and can run even when all pool seats are busy.
     - Manages state persistence across backend instances via `runtime.json` (`seat_panes`).
   - `HerdrBackend`:
     - Resolves `seat_pool` configuration from constructor kwargs, `backend_settings`, or spec.
     - When active, leases a seat from `SeatPool` in `_execute` and passes the leased pane to `_run_in_pane`.
     - Binds D-009 resource events with `kind="seat"`, `id="<seat_label>"`, `label="<seat_label>"`.
     - Writes startup banner to stdout/log before executing worker command in `build_wrapper`:
       `=== [seat:<label>] job:<sprint_id> phase:<phase> agent:<agent_name> ===`.
     - In `finally`, releases the leased seat, including on success, exit failure, exception, timeout, or cancellation.
     - Added `release_job(job)` to clear in-memory seat pool cache at job end.

3. **`runner/backends/__init__.py`**
   - Exported `Seat` and `SeatPool` alongside `HerdrBackend`.

4. **`runner/backends/README.md`**
   - Added `Herdr Seat Pool (D-019)` section detailing configuration, seat assignment, hot seat semantics,
     queueing/timeout, banners, and execution visibility.

5. **`runner/run-hermes-sprint.py`**
   - Forwarded `seat_pool` configuration from `self.spec` or `self.spec["backend_settings"]` to backend factory.

6. **`runner/agents/base.py`**
   - Forwarded `priority` and `persona` from `context.phase` into `ExecutionRequest.metadata`.

7. **`runtime/hermes_adapter.py`**
   - Forwarded `seat_pool` from `task.metadata` or `self.spec` to backend factory.
   - Included `priority` and `persona` in task phase dictionary for adapter execution.

8. **`tests/test_backend_contract.py`**
   - Updated expected backend kwargs set in `test_sprint_runner_selects_new_backend_without_runner_changes`
     to include Phase 1's `cancel_event` and `cancel_grace_seconds`.

9. **`tests/test_backends.py`**
   - Added `FakeHerdrForSeatPool` and `TestHerdrSeatPool` unit test suite covering all required seat pool behaviors.

---

## Configuration Shape

The seat pool is configured in the sprint spec or via backend settings:

```json
"seat_pool": {
  "size": 5,
  "hot": true,
  "acquire_timeout_seconds": 600
}
```

- `size` (int, default `5`): Number of normal fungible pool seats (`seat-1` … `seat-N`).
- `hot` (bool, default `true`): Whether to reserve a dedicated `hot` seat for priority tasks.
- `acquire_timeout_seconds` (float, default `600`): Maximum time to wait for a free seat before raising `FAILED_SEAT_TIMEOUT`.
- **Default off:** When absent or `None`, `HerdrBackend` behaves exactly as before, splitting a new pane per phase.

---

## Tests

Test suite command:
`/home/lystiger/Projects/Hermes-lab/.venv/bin/python -m pytest tests -q --ignore=tests/smoke`
**Result:** 621 passed, 6 skipped, 0 failures.

### New Seat Pool Tests (`TestHerdrSeatPool` in `tests/test_backends.py`):
1. `test_disabled_by_default`:
   Ensures `seat_pool` is None by default, panes are created with phase labels, and resource event kind is `pane`.
2. `test_two_concurrent_phases_get_different_seats`:
   Validates concurrent executions lease distinct seats (`seat-1`, `seat-2`).
3. `test_third_phase_waits_and_gets_released_seat`:
   Validates that when pool capacity is saturated, a third phase waits on the condition and acquires a seat once released.
4. `test_acquire_timeout`:
   Validates that when all seats remain busy beyond `acquire_timeout_seconds`, execution fails closed with `SprintRunnerError("FAILED_SEAT_TIMEOUT")`.
5. `test_hot_seat_only_for_hot_phases_and_available_when_pool_full`:
   Validates that normal phases cannot lease `hot` and time out, while hot phases (`"priority": "hot"`) acquire `hot` immediately even when all pool seats are busy.
6. `test_release_on_failure_and_cancel`:
   Validates seat release on non-zero process exit, backend command exception, and out-of-band cancellation (`cancel_event`).
7. `test_banner_written`:
   Validates that `=== [seat:<label>] job:<sprint_id> phase:<phase> agent:<agent_name> ===` is output at the start of execution and logged to `commands.log`.
8. `test_state_survives_across_backend_instances`:
   Validates that subsequent backend instances and processes load workspace and seat panes from `runtime.json` without re-creating workspace or panes.

---

## What is Left (Follow-ups)

- **Sessionful Hot Seat:**
  The current implementation provides exclusive leases of named panes with clean execution wrappers and banners.
  Maintaining long-lived, continuous agent sessions inside the hot seat (persisting active conversation context across tasks without re-initializing the agent process) was marked out of scope for Phase 2 and remains tracked as a future enhancement.
