# Sprint S08 — Parallel groups: independent verification

Independently verify concurrent execution of `parallel_group` batches. You do
not modify target source; you report.

Check each item with evidence from the code and the test runs:

1. Two phases in one `parallel_group` run their agents at the same time. The
   concurrency test fails on a sequential runner.
2. Phases outside a group, and single-phase batches, run as before.
3. Commits and merges happen one phase at a time, in spec order.
4. A failure in any phase of a batch merges nothing from that batch and stops
   the sprint with the failing phase's code.
5. Shared state (run summary, phase list, backend cache) is not corrupted under
   concurrency. Read the code for unlocked writes.
6. Ownership is still enforced per phase inside a batch.
7. Verifier phases still reject any target change.

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

Replace `HANDOFF_S08_CODEX.md` with one line per item 1 to 7 giving PASS, FAIL
or UNPROVEN, the command or code reference that supports it, and the remaining
risks.

## Final output (required)

Your final message must be one JSON object and nothing else, with no prose
before or after it:

{"verdict": "passed" or "failed", "summary": "<one sentence>", "findings": ["<item and defect>", ...]}

Use "failed" if any item is FAIL or UNPROVEN. The runner reads this object from
your output, so any other output fails the phase.
