# Sprint 05 Independent Verification Handoff

## Outcome

Sprint 05 meets the requested operational API contracts after two narrow,
evidence-supported compatibility fixes and one test-isolation fix.

- `/info` returns exactly the application name, version, and environment:
  `{"name":"Hermes Lab","version":"0.1.0","environment":"development"}`.
- `/ready` returns exactly `{"status":"ready"}`.
- `/metrics` returns non-negative integer `uptime_seconds` and
  `requests_handled` values.
- Uptime derives from `time.monotonic()` and does not decrease.
- Request counting is protected by a lock, includes the current metrics
  request, counts all endpoint requests, and survives a 200-request threaded
  stress test without lost increments.
- `/health` remains exactly `{"status":"ok"}` and `/version` remains exactly
  `{"version":"0.1.0"}`. These were compared with the pre-Sprint-05 baseline
  at `ae984e1` as well as exercised by tests.
- No persistence, Prometheus output, authentication, deployment code, or new
  dependency was added.

## Focused fixes

1. Converted the five route handlers to `async def` without changing response
   bodies or status codes. In the installed FastAPI 0.141.1 / Starlette 1.6.0 /
   AnyIO 4.14.2 environment, an isolated synchronous FastAPI route timed out in
   the AnyIO worker-thread path, while the equivalent async route completed.
2. Replaced Starlette `TestClient` in `test_main.py` with HTTPX's existing
   `ASGITransport`. `TestClient` blocked during context entry in this environment
   and emitted a warning requiring a different client package; adding a new
   dependency was out of scope.
3. Stubbed runner logger setup only in unit-test classes that do not test
   logging. This prevents the gate from trying to create
   `/home/lystiger/hermes-runs` outside the assigned worktree in a read-only
   sandbox. Production runner behavior is unchanged.

## Worker Git boundaries

The existing worker boundaries remain unchanged and are covered by the runner
and backend tests:

- Antigravity permits assigned-worktree edits but denies worktree and canonical
  repository Git-metadata writes, with exact settings restoration.
- Claude receives CLI denials for mutating Git subcommands while read-only Git
  inspection remains available.
- Codex is forced to its assigned `--cd`, `--sandbox workspace-write`, and
  ephemeral execution even if a worker option requests a weaker sandbox.
- Agent adapters contain no controller Git integration; staging, committing,
  merging, deterministic resets, handoff validation, and the final test gate
  remain controller-owned.

## Commands and results

- `git show ae984e1:main.py` — confirmed the preserved `/health` and `/version`
  baseline contracts.
- `git diff ae984e1..HEAD -- main.py test_main.py runner/agents runner/backends tests/test_runner.py tests/test_backends.py`
  — inspected the integrated Sprint 05 delta and confirmed no worker-boundary
  production changes.
- `python -m pytest test_main.py -vv` — **9 passed in 2.30s** after the focused
  fixes.
- Three consecutive `python -m pytest -q test_main.py` runs — **9 passed** in
  2.42s, 2.26s, and 2.24s.
- `python -m pytest -q tests/test_runner.py tests/test_backends.py` — **60 passed,
  1 skipped in 1.15s**.
- `python -m pytest -q -rs` — **69 passed, 1 skipped in 3.51s**; the skip was
  reported as `Herdr server is unavailable`.

Investigation evidence retained for context:

- The initial API test command blocked on its first request. Direct ASGI
  controls showed synchronous handlers timing out and async handlers returning
  normally. After changing the handlers, direct ASGI `/health` returned HTTP
  200 with `{"status":"ok"}`.
- The first full-suite run then reported **24 failed, 45 passed, 1 skipped**;
  every failure was `EROFS` while unit-test construction attempted to create
  `/home/lystiger/hermes-runs`. Stubbing logger setup in the non-logging unit
  tests removed that external write and produced the passing complete gate.

## Remaining risk

- Metrics are intentionally in-memory and process-local. They reset on process
  restart, and a multi-worker deployment would expose per-worker rather than
  globally aggregated values. Fixing that would require persistence or an
  aggregation system explicitly excluded from this sprint.
- The sandbox rejects both TCP and Unix socket binding, so a live Uvicorn socket
  smoke test was unavailable (`could not bind` / `Operation not permitted`).
  Endpoint behavior was instead verified in-process through the ASGI interface,
  including threaded concurrent requests.
- The single skipped test is the pre-existing live Herdr shell smoke test, which
  requires a Herdr-managed pane and reachable server.
