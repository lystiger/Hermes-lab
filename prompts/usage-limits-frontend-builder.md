# Usage limits: console page

You are the BUILDER. Repository: this Hermes runtime. Work in this worktree on the sprint branch. The console app is in `console/` (React 19, Vite, TypeScript, Vitest). Do not touch the Python runtime.

## Goal
The Usage page shows what is left for each agent. The backend already computes the numbers: `GET /capacity/limits` returns `agents[]` with `leftPct`, `usedPct`, `status`, `resetsInSeconds`, `stale`, `plan`, and `windows[]`. Do not recompute the math in the frontend. Display it.

## Page design
- Fewer words. No long "not reported" list. Remove that list from this page.
- One row of four small stats at the top: tokens, requests, success rate, throttling. Use the existing `/capacity/telemetry` data. Show a dash when a value is missing.
- One card per agent, in a responsive grid:
  - Agent name and plan (`plan`) in one line. Status badge: `ok`, `warn`, `alarm`, `stale`, or `not ready`.
  - The big number is `leftPct` with "% left" beside it.
  - A bar showing the remaining share. Colour: `ok` uses the success colour, `warn` the warning colour, `alarm` the danger colour. Use the existing design tokens.
  - Reset line: "resets in 2h 10m" from `resetsInSeconds`. Hide it if there is no reset time.
  - One small row per window: label and `leftPct`.
  - If `ready` is false, show `authHelp` in place of the bar.
- Nothing else on the card.

## Code
- `console/src/api/contracts.ts` (or the matching contracts file): types for the limits response.
- `console/src/api/adapters/httpAdapter.ts`: `getAgentLimits()` calling `/capacity/limits`. Add the matching method to `mockAdapter.ts` with sample data.
- `console/src/api/hooks.ts`: `useAgentLimits()`, refreshing every 60 seconds, following the pattern of `useCapacityTelemetry`.
- `console/src/routes/usage.tsx`: rewrite the page using the design above. Reuse `Card`, `PageHeader` and the state components already in the app.
- `console/src/features/usage/format.ts` (new): pure helpers `formatResetIn(seconds)` (e.g. "2h 10m", "45m", "now") and `statusTone(status)`. Keep them free of React.

## Tests (Vitest)
- `formatResetIn`: 0 → "now", 2700 → "45m", 7800 → "2h 10m".
- `statusTone`: maps each status to its tone.
- A route test that renders two agents from mocked data and shows `86% left`, the reset line, and the `not ready` case with its auth help text.
- Keep existing tests passing. Do not delete or weaken a test to make it pass.

## Gates (all must exit 0, run inside `console/`)
`npm ci`, `npm run typecheck`, `npm run lint` if it exists, `npm test -- --run`.

## Handoff
Write HANDOFF_BUILDER.md with the files changed, the gate results, and anything you are unsure about. Use your file-write tool, not a shell heredoc or redirect. Do not run git commands: the controller stages and commits your changes, and it excludes the handoff file.
