# Sprint S08b — Independent re-verification

Independently re-verify the parallel group changes after the hardener phase. You
do not modify target source; you report.

Check each item with evidence from the code and the test runs:

1. A batch whose second merge fails leaves the integration branch where it
   started. No phase of the batch stays merged.
2. The execution-event queue, execution-owner and fallback-phase writes are
   protected by a lock, and a concurrent test checks them.
3. A verifier phase with a `failed` verdict stops the sprint with a distinct
   status code and never reaches `READY_FOR_REVIEW`. A `passed` verdict and a
   missing verdict on a non-verifier phase keep the existing behaviour.
4. Concurrency still happens: two phases in one `parallel_group` run their agents
   at the same time, and the concurrency test fails on a sequential runner.
5. Commits and merges still happen one phase at a time, in spec order.
6. Ownership is still enforced per phase inside a batch, and verifier phases
   still reject any target change.

## Rules

- Run each test command on its own, with no pipes, `;`, `&&`, `||`, `sed`, or
  redirection. Use exactly these commands:
  - `python3 -m unittest tests.test_runner_parallel`
  - `python3 -m unittest tests.test_runner_ownership`
  - `python3 -m unittest tests.test_runner`
- Do not run any git command, including `git status`, `git diff`, `git stash`
  and `git log`.
- Do not create files inside this worktree other than the handoff.
- Check every item; do not stop at the first failure.

## Handoff

Replace `HANDOFF_S08B_CODEX.md` with one line per item 1 to 6 giving PASS, FAIL
or UNPROVEN, the command or code reference that supports it, and the remaining
risks.

## Final output (required)

Your final message must be one JSON object and nothing else, with no prose
before or after it:

{"verdict": "passed" or "failed", "summary": "<one sentence>", "findings": ["<item and defect>", ...]}

Use "failed" if any item is FAIL or UNPROVEN. The runner reads this object from
your output, so any other output fails the phase.
