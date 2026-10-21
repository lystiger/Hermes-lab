# BUG: Rare cleanup failure in parallel group tests

- **ID:** BUG-s08-parallel-test-cleanup-race
- **Status:** Open. Mitigated by `ignore_cleanup_errors=True`. Root cause not found.
- **Area:** `tests/test_runner_parallel.py` (test teardown only)
- **Severity:** Low. The product code under test is not affected. The test still checks everything before cleanup.
- **Date opened:** 2026-10-21

## Symptom

About once in every 250 to 300 runs, a parallel-group test fails during
temporary-directory cleanup, after its assertions have passed:

```
OSError: [Errno 39] Directory not empty: '/tmp/tmpXXXX/repo/.git'
```

It only appeared when many copies of the test file ran at once (16 parallel
copies). It was never seen in single runs or in 4 and 8-copy runs.

## What the evidence shows

- Each failure left one thing behind under `repo/.git/`: an entry under
  `objects/`. Nothing else was left.
- No process was holding the directory open when the failure was recorded.
- Calling cleanup twice on the same directory was tested and ruled out: 4,320
  cleanup calls across 240 runs, with no directory cleaned more than once.
- The batch code waits for its worker threads (`ThreadPoolExecutor` in a
  `with` block) before returning, so a worker thread still running after the
  test is not the explanation.

## What was not found

- The process or thread that wrote or removed the `objects/` entry.
- Why the entry was still present when cleanup ran.

## Mitigation applied

All 16 `TemporaryDirectory` uses in `tests/test_runner_parallel.py` now pass
`ignore_cleanup_errors=True`. This stops the flaky failure. It also hides any
future real leak of a process that writes into the temp directory during cleanup.
The test assertions are unchanged.

## Evidence summary

| Run | Copies | Runs | Cleanup failures | Notes |
|---|---|---|---|---|
| Barrier-timeout stress | 8 | 48 | 0 | |
| Barrier-timeout stress | 16 | 96 | 1 | Captured, no dump |
| Leak-plugin stress, with retry | 16 | 240 | 1 (hidden by retry) | Dump: `objects/` entry, no live process |
| Leak-plugin stress, no retry | 16 | 240 | 1 | Dump: `objects/` entry, no live process |
| Call-logging stress | 16 | 240 | 0 | 4,320 cleanup calls, none duplicated |

Unresolved link: during the S08b run, `test_rule4_commits_and_merges_occur_one_at_a_time_in_spec_order` failed once in six full-set runs. Its output was not captured, so it may or may not be this bug.

Single-copy and 4-copy runs: 0 failures in 25 runs. Full-set runs at 4, 8 and
16 copies (before the barrier change): 0 failures in 168 runs.

## Time spent

About 40 minutes of wall-clock time, 22:45 to 23:25 on 2026-10-21, mostly
stress runs. This excludes time spent writing scripts and reports.

## Decision and reopen rules

The investigation is closed for now, under the time box above. Reopen it if
any of these happen:

1. The failure rate in the 16-copy stress run rises above about 1 in 100 runs.
2. A cleanup failure appears in a single-copy or normal CI run.
3. A real leaked process is found. `ignore_cleanup_errors` would hide it, so
   remove that flag once the cause is known.
4. Another test file shows the same failure. The flag is only applied to
   `test_runner_parallel.py` so far.

## Where the instrumentation lives

The leak-check and call-logging plugin is a scratch file, not part of the repo:
`scratchpad/leakcheck/leakcheck.py` in the session scratchpad. It is not
committed.
