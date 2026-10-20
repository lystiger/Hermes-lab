# Hermes M11: durable job history

You are the BUILDER. Repository: this Hermes runtime (Python, FastAPI). Work in this worktree on the sprint branch. Do not touch the frontend.

## Problem (measured)
- `JobService` keeps jobs in memory (`self._jobs` in jobs/job_service.py). A restart empties `GET /jobs`, so the console Queue and Overview show nothing.
- Startup recovery (`_recover_recent_runs`) reads only the 30 newest run folders by name, and only those with `run_summary.json`. Of about 1000 run folders, only 4 have a summary, so earlier jobs cannot come back.

## Goal
1. Persist each job record (the same shape `GET /jobs` returns) to disk as JSON, under `runs_root` (per job, e.g. `<runs_root>/<job_id>/job.json`). Write atomically: write a temp file in the same directory, then rename. Write on every state change.
2. On startup, load all persisted jobs, not only 30. Load `run_summary.json` for run folders that have one and no persisted job record. Keep a cap only for safety (e.g. 2000 newest by mtime) and log when it applies.
3. Reconcile on startup: a job persisted as running (CREATED, PREPARING, PLANNING, EXECUTING, VERIFYING, etc.) has no live process after a restart. Mark it FAILED with an error message "interrupted by runtime restart". Do not add a new status value, because the console maps existing statuses.
4. A corrupt or unreadable record is skipped with a logged warning. It must not stop startup.
5. The `GET /jobs`, `GET /jobs/{id}` and related response shapes must not change.

## Constraints
- Do not launch agents or change the runner's behaviour. Do not change `/jobs` response shapes.
- Keep writes off the event loop's hot path if they are slow; a small JSON write per state change is acceptable.
- Standard library only for new code.

## Tests (pytest, under tests/)
- A job written and reloaded round-trips to the same summary.
- A job that was running before a restart is reconciled to FAILED with the interrupted message.
- A corrupt record is skipped and startup continues.
- A run folder with only `run_summary.json` is loaded when no record exists.
- Atomic write: a failed write leaves the previous record intact.

## Gates
`/home/lystiger/Projects/Hermes-lab/.venv/bin/python -m pytest tests -q --ignore=tests/smoke -p no:cacheprovider` exits 0 (use the venv, not the system python).

## Handoff
Write HANDOFF_BUILDER.md: files changed, the record location and format, the reconciliation rule, test results, and anything uncertain. Commit with the message `feat(runtime): persist job records and reload them on restart`, ending with `Co-Authored-By: Claude Haiku 5.5 <noreply@anthropic.com>`.
