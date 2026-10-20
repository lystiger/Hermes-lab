# LysControl M9: start the event stream after the first requests settle

You are the BUILDER. Repository: the LysControl console (React 19, Vite, TypeScript, Zustand, Vitest). Your worktree is the target repo on this sprint's branch.

## Problem (measured)
On a cold full-page load the console stalls intermittently. `useEventStream` (src/api/hooks.ts) opens the Server-Sent Events stream (`hermesApi.subscribeEvents` in src/api/adapters/httpAdapter.ts) while the page's first burst of GET requests is still going. Chrome allows about six connections per host, so the open stream plus the burst leaves requests queued for seconds.
Measured: 6 of 42 cold loads stalled with the stream open; 0 of 42 with the stream blocked; 1 of 42 with a fixed 1.5 s delay. The delay was an experiment only.

## Goal
Open the event stream once the page's first burst of requests has settled, using a principled trigger, not a timer.
- Keep health and history first, as now. Then wait until the adapter has no requests in flight (add a small in-flight counter in `request()`, which already wraps fetch, plus a way to wait for idle), then call `subscribeEvents` with the same cursor (newest history id).
- No events may be lost in the gap: the stream resumes from the history cursor.
- If the stream drops, the existing reconnect and resync behaviour must still work.
- Keep REQUEST_TIMEOUT_MS and the shared-load behaviour from the previous commit.

## Constraints
- Do not change the Agents data model (M6). Do not weaken existing tests; if an assertion must change because the behaviour legitimately changed, say so in the handoff.
- Do not add timers used as the fix.

## Tests to add
A focused test file (e.g. src/__tests__/m9-stream-start.test.tsx): the stream is not opened while requests are in flight; it opens after they settle; the cursor is the newest history id.

## Required gates (all must exit 0)
npm run typecheck, npm run lint, npm run test -- --run, npm run build.

## Handoff
Write HANDOFF_BUILDER.md in the worktree root: files changed, the trigger you chose and why, test results, and anything uncertain. Commit with the message: `fix(console): open the event stream after the first requests settle`, ending with the trailer `Co-Authored-By: Claude Haiku 5.5 <noreply@anthropic.com>`.
