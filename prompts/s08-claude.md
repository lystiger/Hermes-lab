# Sprint S08 — Parallel groups: implementation

Implement concurrent execution of `parallel_group` batches in
`runner/run-hermes-sprint.py`, so that `tests/test_runner_parallel.py` passes.
That file, written by the previous phase, is the specification. Do not weaken
or delete its tests. If one contradicts the rules in `prompts/s08-agy.md`,
change the test only to match those rules, and say so in your handoff.

Rules to implement (full wording in `prompts/s08-agy.md`):

- Group consecutive phases that share a `parallel_group` into one batch.
- Run the agent of each phase in a batch concurrently, each in its own worktree,
  for example with a thread pool. Prepare every worktree before the pool starts,
  and keep each phase's run in its own worktree only.
- Keep all shared state safe under concurrency: the run summary, the phase
  list, the logger calls that record phase results, and the backend cache.
  Guard shared writes with a lock, or collect results and write them after the
  pool finishes.
- Serialize the post-run steps: change validation, ownership enforcement,
  commit, and merge into the integration worktree. Run them one phase at a time
  in spec order, after every agent in the batch has finished.
- If any phase in a batch fails, merge nothing from that batch, record the
  failing phase's code, and stop the sprint with that code.
- Keep sequential phases and single-phase batches on the existing code path,
  with unchanged behaviour.

Constraints:

- Split the current `execute_phase` into two parts: the agent run, and the
  post-run integration. Keep the public behaviour of a single phase the same.
  Keep the diff local to those functions and the phase loop in `execute`.
- Match the file's style: its status codes, error messages and logging.
- Update `runner/README.md` with one short section on how batches run, next to
  the existing `parallel_group` note.
- Do not add a dependency. Use the standard library only.

Shell rules for this run, because the controller denies anything else:

- Do not run any git command, including `git status`, `git diff`, `git stash`
  and `git log`. Use your file-reading tools to inspect changes.
- Run each test command on its own, with no pipes, `;`, `&&`, `||`, `sed` or
  redirection. Use exactly these commands:
  - `python3 -m unittest tests.test_runner_parallel`
  - `python3 -m unittest tests.test_runner_ownership`
  - `python3 -m unittest tests.test_runner`
- Edit files with your file-editing tools, not with `sed -i`.

Replace `HANDOFF_S08_CLAUDE.md` with: the functions you changed and how each
batch now runs, the test results you observed, any test you changed and why,
and anything you could not run.

Do not commit, merge, rebase, push, edit Git metadata, or operate outside this
assigned worktree. The controller owns all Git operations.
