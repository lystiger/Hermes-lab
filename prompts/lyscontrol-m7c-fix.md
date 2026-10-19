# Role: BUILDER — LysControl M7c: fix the review findings

You are the BUILDER. Hermes owns Git. Do not run git add, commit, merge, push,
reset, checkout, or alter Git metadata. Work only in your assigned worktree.

First: run `npm ci`. Read `HANDOFF_AGY.md` (what the first pass did) and
`HANDOFF_HARDENER.md` (a review of that pass with file and line references),
then `docs/console-spec.md`. Do not redo the redesign; fix what the review
found. Keep everything real: no invented values, unknown stays `—`.

## Fix list (each item has a line reference in HANDOFF_HARDENER.md)

1. **Unbounded event and error text.** Clamp to 2 lines in lists with the full
   text in a `title` tooltip or an expand control: Overview live trace
   (`src/routes/index.tsx`), job inspector trace (`JobDetailView.tsx`),
   failure lines and task/run errors (`JobRealData.tsx`), `ErrorState` and
   `StaleNotice` (`DataStates.tsx`). A failed task's error can contain a full
   multi-paragraph prompt; it must never take over a page.
2. **Usage duplicates.** The stat strip and the cards repeat tokens, success
   rate and throttling. Keep each value once.
3. **Queue empty columns.** Collapse empty status groups into a compact strip
   (name and count) and give the space to groups that have jobs. Columns in a
   row should be equal height.
4. **Stat strip.** Reserve its height before data arrives (no layout shift).
   Align baselines of values and units; use one unit style, including zero.
5. **Nested interactive elements.** `queue.tsx` wraps `CopyId` (a button) in a
   button. Make the row a link or a div with a keyboard handler, not a button
   containing a button.
6. **Copy limits.** Usage subtitle at most 3 words (the "since runtime start"
   qualifier moves to the info tooltip or a short note). Job inspector empty
   states at most 5 words (`JobRealData.tsx`). Settings should show an
   "updated" stamp like the other pages. Usage must show a stale notice when a
   refresh fails and cached data is shown.
7. **Dead CSS.** Remove `bg-cyber-grid` if nothing uses it. Keep `clip-hex`,
   `clip-armor` and `bg-striped-pattern` while they have consumers.

## Guard tests (add them)

- `src/__tests__/no-placeholders.test.ts`: scan `src/components`, `src/routes`,
  `src/features`, `src/stores` and `src/api/adapters/httpAdapter.ts` (not
  `src/api/mock`, not tests). Fail on: `#142`, `VehicleStateStore`,
  `moveinmate`, `$4.12`, `58%`, `SIMULATED`, `~37 min`, `v0.1.0`, `raise cap`,
  `alert(`, `Phase 4`, `Not reported by Hermes`.
- A test that renders the event-text clamp with a 2,000-character message and
  asserts it is clamped and still reachable (title or expand).
- Update any test that pins removed copy; do not delete a test without
  replacing its intent.

## Constraints

- Do not change the Hermes API contract. No new runtime dependency.
  `architecture.test.ts` must keep passing.
- Use only these commands: `npm ci`, `npm run typecheck`, `npm run lint`,
  `npm test`, `npm run build`. Do not start servers.

## Done means

typecheck, lint, test and build all pass.

## Handoff

Create `HANDOFF_FIX.md`: per numbered item what changed (file), tests added,
anything not done and why. Stop after the handoff.
