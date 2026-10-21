# Sprint S08 — Parallel groups: hardening

You are the HARDENER. The batch implementation in `runner/run-hermes-sprint.py`
and its tests are already in this worktree. Look for concrete defects only:
races, lost results, a batch that merges after a failure, a phase that runs
before its worktree is ready, a barrier test that passes for the wrong reason.
Fix only those, with tests. Do not restyle or refactor.

Specifically check:

1. Shared state written from more than one thread: the run summary, the phase
   list, and the backend cache. Each write must be locked or collected.
2. Post-run steps (validation, ownership, commit, merge) run serially, in spec
   order, and only after every agent in the batch has finished.
3. A failure in any phase stops the batch before any merge, and the failing
   phase's code is the one recorded.
4. A single-phase batch and a sequential phase take the same path as before.
5. The concurrency test really needs both agents to run at once. A sequential
   runner must fail it.
6. Ownership is still enforced per phase inside a batch.

## Rules

- Keep each fix local. No new abstractions.
- Do not weaken or delete tests. You may add tests.
- Run each test command on its own, with no pipes, `;`, `&&`, `||`, `sed`, or
  redirection. Use exactly these commands:
  - `python3 -m unittest tests.test_runner_parallel`
  - `python3 -m unittest tests.test_runner_ownership`
  - `python3 -m unittest tests.test_runner`
- Do not run any git command, including `git status`, `git diff`, `git stash`
  and `git log`.
- Edit files with your file-editing tools, not with `sed -i`.

## Handoff

Replace `HANDOFF_S08_HARDENER.md` with, for each check 1 to 6: the status (fixed,
or not fixed with the reason), the test that covers it, and the function you
changed. Name anything you could not run.

Do not commit, merge, rebase, push, edit Git metadata, or operate outside this
assigned worktree. The controller owns all Git operations.
