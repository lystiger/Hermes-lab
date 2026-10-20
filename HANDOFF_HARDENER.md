# Hermes M11 hardener handoff

## Defect and fix

One concrete defect: migrated legacy runs consumed the recovery cap twice. Startup
creates `run_<legacy-folder>/job.json` alongside the original summary folder. The
next startup capped folders before suppressing duplicate IDs. Newer original
summaries could exclude the durable records, rebuilding jobs with old details and
new creation timestamps; mixed ordering could exclude other jobs altogether.

`jobs/job_service.py` now suppresses summary folders with corresponding record
folders before sorting and applying the cap. Persisted records retain precedence.
No response fields or runner behavior changed.

Regression: `tests/test_job_persistence.py::test_legacy_migration_does_not_consume_recovery_cap_twice`.
Reproduction uses a cap of three, three legacy runs, migration, a title update
absent from the summaries, and summary mtimes newer than every record folder.
It asserts all restarted summaries equal their persisted versions. Before the
fix, the initial regression produced `1 failed, 25 passed`, with `AssertionError`
on `assert second == first` and `Job recovery capped at 3 newest run folders (6 found)`.
After the fix, the strengthened regression and existing persistence suite pass.

## Validation

- `/home/lystiger/Projects/Hermes-lab/.venv/bin/python -m pytest tests/test_job_persistence.py -q -p no:cacheprovider`: **26 passed in 0.93s**.
- `git diff --check`: passed.
- Required gate executed exactly:
  `/home/lystiger/Projects/Hermes-lab/.venv/bin/python -m pytest tests -q --ignore=tests/smoke -p no:cacheprovider`.
  It stopped progressing after 23 dots and was interrupted (exit 130).
  Log: `/tmp/hermes-m11-hardener-gate.log`. No full-gate pass claimed.
- Isolated reproduction:
  `/home/lystiger/Projects/Hermes-lab/.venv/bin/python -m pytest tests/test_backend_contract.py::test_runtime_dispatches_new_backend_and_releases_it_once_on_success -vv -p no:cacheprovider -o faulthandler_timeout=10`.
  Output: `Timeout (0:00:10)!`; main thread in `selectors.py:452 in select`,
  through `tests/test_backend_contract.py:200 in _run_task`; asyncio worker idle
  in `concurrent/futures/thread.py:116 in _worker`. Interrupted, exit 130.
  Log: `/tmp/hermes-m11-hardener-hang.log`. Matches the builder's documented hang.
- Additional related-suite attempt (`test_job_end_release.py`,
  `test_phase9_api_and_durability.py`, `test_phase9_1_durability.py`) also stalled
  without results and was interrupted, exit 130. No passing claim for it.

## Commit

Requested trailer: `Co-Authored-By: Claude Haiku 5.5 <noreply@anthropic.com>`.

Commit blocked: `git add jobs/job_service.py tests/test_job_persistence.py HANDOFF_HARDENER.md`
exited 128:
`fatal: Unable to create '/home/lystiger/Projects/Hermes-lab/.git/worktrees/hardener/index.lock': Read-only file system`.
No commit created. Intended message:

```text
fix(runtime): deduplicate migrated jobs before recovery cap

Co-Authored-By: Claude Haiku 5.5 <noreply@anthropic.com>
```
