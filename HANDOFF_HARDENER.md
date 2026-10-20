# Hermes M11 hardener handoff

Reviewed the durable job implementation and builder continuation at cc1553b.
Two concrete defects fixed in `jobs/job_service.py`, each with a regression in
`tests/test_job_persistence.py`:

1. Startup reconciled the job and phases but left serialized tasks RUNNING.
   Recovery now marks running task dictionaries FAILED and sets `completed_at`
   to the reconciled job completion timestamp. Completed tasks remain intact.
   `test_restart_reconciles_running_task_records` checks both task states and
   persistence across a second restart.
2. Engine snapshots did not copy observations from the engine registry. A
   committed observation event with no live event bus left `job.json` with an
   empty observations array, losing the observation on restart. Snapshotting now
   copies the job's registry observations before persisting.
   `test_reactive_observation_survives_restart_without_polling` uses a real
   engine, isolated registry, and bridge without a bus; checks the file before
   any endpoint read and verifies recovered observations.

Before fixes, the focused suite reported `2 failed, 28 passed in 1.12s`:
- `assert tasks[0]["status"] == "FAILED"`: `AssertionError: assert 'RUNNING' == 'FAILED'`.
- `assert data["observations"] == [observation.to_dict()]`: `AssertionError: assert [] == [{'observation_id': ...}]`.
Reproduction: run the focused command below with the regression tests and without
these source fixes.

Validation:
- `/home/lystiger/Projects/Hermes-lab/.venv/bin/python -m pytest tests/test_job_persistence.py -q -p no:cacheprovider`:
  **30 passed in 0.95s** after fixes.
- `git diff --check`: passed.
- Required gate executed:
  `/home/lystiger/Projects/Hermes-lab/.venv/bin/python -m pytest tests -q --ignore=tests/smoke -p no:cacheprovider`.
  Stalled after 23 dots; interrupted, exit **130**. No full-gate pass claimed.
  Log: `/tmp/hermes-m11-hardener-current-gate.log`.
- Isolated reproduction:
  `/home/lystiger/Projects/Hermes-lab/.venv/bin/python -m pytest tests/test_backend_contract.py::test_runtime_dispatches_new_backend_and_releases_it_once_on_success -vv -p no:cacheprovider -o faulthandler_timeout=10`.
  `Timeout (0:00:10)!`; main thread in `selectors.py:452 in select`, through
  `tests/test_backend_contract.py:200 in _run_task`; executor worker idle in
  `concurrent/futures/thread.py:116 in _worker`. Interrupted, exit **130**.
  Matches the hang documented in the builder handoff.
  Log: `/tmp/hermes-m11-hardener-current-hang.log`.

No DTO fields or response shapes changed. Atomic write and legacy deduplication
regressions remain passing in the focused suite.

Commit blocked by workspace permissions. `git add jobs/job_service.py
tests/test_job_persistence.py HANDOFF_HARDENER.md` exited 128:
`fatal: Unable to create '/home/lystiger/Projects/Hermes-lab/.git/worktrees/hardener/index.lock': Read-only file system`.
No commit created. Intended commit message:

```text
fix(runtime): persist observations and reconcile interrupted tasks

Co-Authored-By: Claude Haiku 5.5 <noreply@anthropic.com>
```
