# Hermes M11 builder handoff

Files changed:
- `jobs/job_service.py`: atomic snapshots, startup recovery, reconciliation, live engine snapshot hooks.
- `jobs/job_state_reducer.py`: persist after event reduction.
- `runtime/events.py`: optional committed-event listeners; failures are logged and do not affect execution/publication.
- `tests/test_job_persistence.py`: persistence and recovery regression coverage.
- `HANDOFF_BUILDER.md`: this handoff.

Records live at `<runs_root>/<job_id>/job.json`. Each UTF-8 JSON object contains the existing full `JobDetailDTO.to_dict()` shape, including every summary field, phases, tasks, artifacts, errors, and observations. Endpoint response shapes are unchanged. Changed snapshots are written to a unique same-directory temporary file, flushed and fsynced, then replaced with `os.replace`; failures warn, preserve the previous record, and permit retries. Unchanged snapshots skip disk writes.

Startup scans all folders containing records or legacy summaries, capped at the 2000 newest folders by directory mtime with a warning. Records take precedence. Summary-only folders are reconstructed and persisted; duplicate historical IDs are suppressed. Malformed/unreadable records warn and are skipped independently.

Reconciliation preserves COMPLETED, BLOCKED, FAILED, and CANCELLED. Every other persisted status becomes FAILED, gets a completion timestamp and `errors` entry `{"error": "interrupted by runtime restart"}`. Running/preparing phases also become FAILED. The reconciled snapshot is persisted, making repeat startup idempotent.

Verification:
- Current focused persistence suite: 28 passed in 1.38s. Added explicit regressions for recovering 40 persisted records and avoiding writes on unchanged reads. The implementation was already present in HEAD at the start of this continuation.
- Required command: `/home/lystiger/Projects/Hermes-lab/.venv/bin/python -m pytest tests -q --ignore=tests/smoke -p no:cacheprovider`. It stalled after 23 tests in `tests/test_backend_contract.py::test_runtime_dispatches_new_backend_and_releases_it_once_on_success`; interrupted, exit 130. No passing full-gate claim is made.
- The unchanged HEAD exported to `/tmp/hermes-m11-baseline` reproduces that hang. Faulthandler shows the main thread in `selectors.select` and the `asyncio_0` worker idle. Minimal reproduction: `timeout -s INT 8 /home/lystiger/Projects/Hermes-lab/.venv/bin/python -c 'import asyncio; asyncio.run(asyncio.to_thread(lambda: 42)); print("thread completion delivered")'` also timed out (124).
- Diagnostic-only selector polling workaround in `/tmp/hermes_m11_poll.py` allowed further tests to execute; it is not repository code and is not the required gate. Both the working tree and unchanged baseline report `1 failed, 12 passed` for `PYTHONPATH=/tmp /home/lystiger/Projects/Hermes-lab/.venv/bin/python -m pytest tests/test_backend_contract.py -q -p no:cacheprovider -p hermes_m11_poll --maxfail=1`. Shared failure: `test_sprint_runner_selects_new_backend_without_runner_changes`, `OSError: [Errno 30] Read-only file system` creating `/home/lystiger/hermes-runs/<timestamp>_lab-s03`. Full diagnostic runs also encountered failures and were stopped; they are not regression-free evidence.
- Diagnostic logs: `/tmp/hermes-m11-baseline-result.txt`, `/tmp/hermes-m11-first-failure.txt`, `/tmp/hermes-m11-baseline-first-failure.txt`, `/tmp/hermes-m11-diagnostic-suite.txt`, `/tmp/hermes-m11-baseline-suite.txt`.
- Current required gate rerun stalled after 23 passing tests at the same backend test; interrupted, exit 130. A verbose diagnostic rerun with `-o faulthandler_timeout=15` confirms the main thread blocked in `selectors.select` and the executor worker idle. Log: `/tmp/hermes-m11-builder-gate.log`. The standalone `asyncio.to_thread(lambda: 42)` reproduction also timed out again (124). The full gate remains unpassed.
- `git diff --check`: passed.

Limits: small JSON writes are synchronous, with fsync; no slow-filesystem performance benchmark was run. Writes fail open with warnings if storage is unavailable. Historical run folders without either a record or a summary cannot be reconstructed. The event bridge listener observes state only; execution policy, adapters, runner behavior, and frontend are unchanged. The atomic rename contract is covered; parent-directory fsync for sudden power loss is not provided.

The earlier implementation commit `908ace5` and hardening commit `f360507` are already ancestors of current HEAD. Committing this continuation is blocked by workspace permissions: `git add` exits 128 with `fatal: Unable to create '/home/lystiger/Projects/Hermes-lab/.git/worktrees/builder/index.lock': Read-only file system`. No commit was created. Intended commit message:

```text
feat(runtime): persist job records and reload them on restart

Co-Authored-By: Claude Haiku 5.5 <noreply@anthropic.com>
```
