# Sprint 05 Handoff — Claude (Hardening Phase)

## Scope

Replaced Antigravity's placeholder `/metrics` values (`uptime_seconds`/`requests_handled`
always `0`) with real process-local behavior, per `HANDOFF_AGY.md` pending work.
`/health`, `/version`, `/info`, `/ready` untouched (no regression).

## Design choices

- **Uptime**: `_start_monotonic = time.monotonic()` captured once at module import
  (process start). `/metrics` computes `uptime_seconds = max(0, int(time.monotonic() -
  _start_monotonic))`. `time.monotonic()` is immune to wall-clock adjustments (NTP,
  DST), so uptime is always non-negative and non-decreasing within one process
  lifetime. `max(0, ...)` is defensive floor only — clamps a negative delta if the
  clock source ever misbehaves; does not mask real bugs since monotonic clocks don't
  go backward. `int()` truncates toward zero, so integer contract holds.
- **Request counting**: `@app.middleware("http")` wraps every request (all routes,
  not just `/metrics`), increments a module-level `_request_count` guarded by
  `threading.Lock`, then calls the next handler. FastAPI's default sync `TestClient`/
  `uvicorn` worker model can serve requests from multiple threads (sync def handlers
  run in a threadpool), so the lock makes increments atomic under concurrent load.
- **Current request inclusion**: middleware increments *before* `call_next`, so by
  the time the `/metrics` handler reads the counter, the in-flight `/metrics` request
  is already counted — satisfies "count visible from `/metrics` includes the current
  metrics request" without special-casing the route.
- **No new dependencies**: only stdlib (`threading`, `time`) added; `requirements.txt`
  unchanged.

## Changed files

- `main.py`: added `count_requests` middleware, `_start_monotonic`, `_request_count`,
  `_request_count_lock`; rewrote `/metrics` handler to compute live values.
- `test_main.py`: replaced the placeholder-exact-match `test_metrics` assertion with
  a schema/type/non-negativity check, and added:
  - `test_metrics_uptime_nondecreasing` — two `/metrics` calls ~1.1s apart, asserts
    strictly increasing uptime (proves monotonic wall-time tracking, not a frozen 0).
  - `test_metrics_requests_handled_includes_current_request` — two consecutive
    `/metrics` calls, asserts count increases by exactly 1 (proves the metrics
    request itself is counted).
  - `test_metrics_requests_handled_never_decreases_and_counts_all_requests` — calls
    `/health`, `/version`, `/info`, `/ready` then `/metrics`, asserts the delta
    equals exactly the number of requests issued (proves middleware counts every
    route, not just `/metrics`).
  - `test_metrics_requests_handled_concurrency_safe` — 20 threads x 10 requests each
    against `/health`, asserts the final count is exactly `baseline + 200 + 1`
    (proves the lock prevents lost updates under concurrent load).

## Test results

```
python3 -m pytest -q
70 passed, 1 warning in 5.22s
```

Warning is pre-existing/unrelated (`httpx` deprecation notice from `starlette.testclient`).

## Remaining verification risks

- Concurrency test uses Python threads via `TestClient`, which exercises the same
  in-process lock path a multi-worker `uvicorn` deployment would not — the lock only
  protects against thread-level races within one process. A multi-process deployment
  (e.g. `uvicorn --workers N`) would need per-process counters or a shared store
  (Redis, etc.); out of scope per "dependency-free" and "process-local" instructions.
- Uptime test relies on a real 1.1s sleep to observe an integer-second increment;
  this is deterministic but adds ~1s to the test suite runtime.
- No load test beyond 200 concurrent-ish requests; higher concurrency or async-def
  handlers (which would run on the event loop instead of the threadpool) are
  untested but would still be protected by the same lock since the middleware
  itself is async and increments are still lock-guarded.
