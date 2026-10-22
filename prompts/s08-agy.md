# Sprint S08 — Parallel groups: contract tests

Write the failing tests that specify how the sprint runner executes phases that
share a `parallel_group`. Do not change `runner/run-hermes-sprint.py`; the next
phase implements it.

Put the tests in a new file `tests/test_runner_parallel.py`. Read
`tests/test_runner_ownership.py` first and follow its style and helpers.

Specify these rules:

1. Consecutive phases with the same `parallel_group` form one batch. Phases in
   a batch run their agents at the same time, each in its own worktree.
2. Phases without `parallel_group` run one at a time, as today.
3. Concurrency is proven by a test where two phases in one group are both
   running at the same moment. Use a barrier or event that only releases when
   both agent runs have started; a sequential runner would time out the barrier.
4. Commits and merges into the integration worktree happen one phase at a time,
   in spec order, never concurrently.
5. If any phase in a batch fails, no phase in that batch is merged. The sprint
   stops with that phase's failure code. Phases that already finished are not
   merged.
6. A batch still obeys each phase's `owned_paths` rule: a builder that changes a
   file outside its own prefixes fails with `FAILED_OUTSIDE_OWNERSHIP`, and the
   batch merges nothing.
7. A batch with one phase behaves exactly like a sequential phase.
8. The run summary lists the phases of a batch in spec order.

Use a fake agent in the tests. Do not start real agent CLIs, do not use the
network, and do not run Git commands against the real repository; create a
temporary repository in each test, as the ownership tests do.

Tests must fail for the right reason today (no concurrency exists), not because
of syntax or import errors. Keep the change to that one test file.

Use only your file-reading and file-writing tools. Do not run any shell command,
including `find`, `grep`, `python` or `pytest`: shell commands are denied in this
run. Do not run the tests; the next phase and the verifier run them.

The last step is mandatory: write `HANDOFF_S08_AGY.md` with your write-file tool.
The phase fails without it, even if the test file is complete. In it, list each
test, the rule it covers, and why it fails today.
