# Sprint S08b — Harden parallel group execution

You are the HARDENER. The parallel batch implementation is already in this
worktree, and it passes its tests. An independent verifier found three defects.
Fix only these, with tests. Do not redesign, do not restyle, do not refactor.

## Defects to fix

1. **Batches are not atomic at integration.** If a later phase's merge into the
   integration worktree fails, earlier phases of the same batch stay merged. A
   batch must merge all of its phases or none. Choose one approach and keep it
   small: either roll the integration branch back to its tip from before the
   batch when a later merge fails, or check every phase's merge applies cleanly
   before merging any. Add a test where the second merge of a batch fails and
   the integration branch ends where it started.
2. **Shared state is written without a lock.** The execution-event queue
   initialisation can create competing queues when two threads race, and the
   execution-owner and fallback-phase writes are unlocked. Guard each write with
   the lock the runner already uses for run-summary state, or add one if there is
   none. Add a test that runs these writes from concurrent threads and checks that
   exactly one queue exists and no write is lost.
3. **A failed verifier verdict does not block the result.** The runner records
   the verifier's verdict in the phase's runtime metadata, but the sprint still
   finishes as `READY_FOR_REVIEW` when the verdict is `failed`. Make a verifier
   phase whose verdict is `failed` stop the sprint with a distinct status code, and
   make it not reach `READY_FOR_REVIEW`. A `passed` verdict or no verdict on a
   non-verifier phase keeps today's behaviour. Add tests for `failed`, `passed`
   and missing verdict.

## Rules

- Keep each fix local to the function it concerns. No new abstractions. Standard
  library only.
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

Replace `HANDOFF_S08B_CLAUDE.md` with, for each defect 1 to 3: the status (fixed,
or not fixed with the reason), the tests that cover it, and the functions you
changed. Name anything you could not run.

Do not commit, merge, rebase, push, edit Git metadata, or operate outside this
assigned worktree. The controller owns all Git operations.
