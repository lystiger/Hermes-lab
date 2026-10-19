# Role: BUILDER — LysControl M7d: three defects

You are the BUILDER and you may edit source files. Hermes owns Git: do not run
git add, commit, merge, push, reset, checkout, or alter Git metadata. Work only
in your assigned worktree. Run `npm ci` first. Use only `npm ci`,
`npm run typecheck`, `npm run lint`, `npm test`, `npm run build`, plain
`grep`/`ls`. Do not start servers. Edit files directly; do not `cd` or run
inline scripts.

Read `docs/console-spec.md` for the rules (real data only, unknown stays `—`).

## Defect 1: real job statuses are not recognised (most important)

Hermes reports these job statuses (uppercase on the wire, from
`GET /jobs`): CREATED, PLANNING, EXECUTING, WAITING_FOR_CAPACITY, VERIFYING,
REPAIRING, COMPLETED, BLOCKED, FAILED, CANCELLED.

The console does not know EXECUTING. While a job is executing: the Queue stat
strip shows "Running 0", the mission board puts the job under "Other ·
Executing", and Overview says "No active execution". Fix:

- `src/api/types.ts` `JobStatus`: add the missing real statuses.
- `src/api/adapters/httpAdapter.ts`: `ACTIVE_JOB_STATUSES` (line ~42) and the
  telemetry counts (running, queued, blocked, failed) must classify every real
  status: running = EXECUTING, PLANNING, VERIFYING, REPAIRING (and the
  existing RUNNING, PREPARING); queued = CREATED, QUEUED, CLAIMED,
  WAITING_FOR_CAPACITY; terminal = COMPLETED, FAILED, CANCELLED; BLOCKED.
  Keep one source of truth for the grouping; the mission board
  (`MissionBoard.tsx`), `routes/queue.tsx`, `routes/index.tsx` (Overview
  active execution) and the sidebar badge must all use it.
- No job may land in an "Other" group unless its status is genuinely unknown
  to the console; an unknown status shows its raw text.
- Add tests: each real status maps to the expected group; a job with status
  EXECUTING counts as running and appears in Overview "active execution".

## Defect 2: overlap on the Execution page at 1280 px

`src/features/execution/ExecutionResourceCard.tsx` (around lines 55-56) puts
`job <id>` and `task <id>` on one line; with long ids they collide at 1280 px.
Put job and task on separate lines (or stack them), truncate each with a
`title` tooltip, and keep the card grid equal-width. The layout scan
`scripts/ui-check.mjs` reported: overlap between the job id span and the task
id span at 1280/execution.

## Defect 3: empty state too long

`src/features/jobs/JobDetailView.tsx` around line 38: the message shown when no
job is loaded and there is no error is longer than 5 words. Shorten to at most
5 words (for example "No job selected").

## Done means

typecheck, lint, test and build pass. Write `HANDOFF_FIXES.md`: per defect
what changed (file), tests added, anything not done and why. Stop after the
handoff.
