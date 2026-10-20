# HANDOFF_BUILDER: Usage limits console page

## Files changed (all under `console/`)
- `src/api/types.ts`: `AgentLimit`, `AgentLimitWindow`, `AgentLimitsReport`.
- `src/api/contracts.ts`: `getAgentLimits()` on `HermesApi`.
- `src/api/mapping.ts`: `mapAgentLimits` (shape checks only, no maths).
- `src/api/adapters/httpAdapter.ts`: `getAgentLimits()` calls `/capacity/limits`.
- `src/api/adapters/mockAdapter.ts`: `getAgentLimits()` with two sample agents.
- `src/api/hooks.ts`: `useAgentLimits()`, refetches every 60 s.
- `src/features/usage/format.ts` (new): `formatResetIn`, `statusTone`.
- `src/routes/usage.tsx`: rewritten (4 stats in the header, one card per agent, no not-reported list).
- Tests: new `src/features/usage/format.test.ts`, new `src/__tests__/usage-limits-route.test.tsx`.
- Support: `src/__tests__/support/liveHermes.ts` now answers `/capacity/limits` (default: no agents).

## Existing tests I had to change (please review)
The old Usage page content was pinned by tests, which conflicts with the new design. Nothing was deleted or loosened beyond this:
- `m7-empty-routes.test.tsx`: `/usage` empty state is now `No agent limits` (was `No provider usage`); added a `getAgentLimits` mock.
- `m1-truth-routes.test.tsx` "Usage: ...": asserted the removed `run budget` and `Unreported metrics` text. It now asserts they are absent, plus the empty state and the no-fabrication check.
- `m3-readable.test.tsx` "M3 usage: meters...": the provider meters are no longer on the page. The test now renders `ProviderMeters` through a small harness, so its meter assertions are kept. I dropped the one assertion about the stat strip's `75`, which belonged to the old page.

## Gates (run in `console/`)
- `npm ci`: exit 0
- `npm run typecheck`: exit 0
- `npm run lint`: exit 0
- `npm test -- --run`: **exit 1**. 284 passed, 2 failed. Both failures exist on the untouched branch (checked before my edits) and are in `m4b-redesign.test.tsx`: the agent avatar/card image files and the Hermes emblem file are missing from the worktree. Not related to this work.

## Unsure about
- The "since runtime start" qualifier is no longer visible text (fewer words). It is a hover title on the four stats.
- Status badge precedence: `not ready` > `stale` > backend `status`. The bar colour follows the backend `status` even when stale.
- The card hides the reset line when `resetsAt` is null (the backend sends `resetsInSeconds: 0` then, so it can't be used to tell).
- Telemetry errors are not shown; the stats just show dashes. Only limits errors get an error/stale state.
- `HeaderNotReported` / `NotReported` are untouched and still used by other routes.
