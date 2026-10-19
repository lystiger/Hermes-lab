# Role: VERIFIER — LysControl M7

You are the VERIFIER. Hermes owns Git orchestration. Do not run git add,
commit, merge, push, reset, checkout, or alter Git metadata. Work only in your
assigned worktree. Builder and hardener results plus `HANDOFF_AGY.md` and
`HANDOFF_HARDENER.md` are already present. Do not trust the handoffs; verify.

## Objective

Independently verify the LysControl M7 redesign and add automated guards so
regressions are caught. Fix small defects you find; report larger ones.

## Tasks

1. Run `npm ci`, `npm run typecheck`, `npm run lint`, `npm test`,
   `npm run build`. Record results.
2. **Placeholder guard.** Add `src/__tests__/no-placeholders.test.ts`: scan
   the source text of `src/components`, `src/routes`, `src/features`,
   `src/stores` and `src/api/adapters/httpAdapter.ts` (not `src/api/mock`, not
   tests) and fail if any of these appear: `#142`, `VehicleStateStore`,
   `moveinmate`, `$4.12`, `58%`, `SIMULATED`, `~37 min`, `v0.1.0`, `raise cap`,
   `alert(`, `Phase 4`, `Not reported by Hermes`, `since runtime start (process`
   more than once per file. Skip a check if an equivalent test already exists.
3. **Real-mode render test.** With the API client mocked to return empty lists
   and a health response, render each route (`/`, `/queue`, `/agents`,
   `/usage`, `/events`, `/execution`, `/settings`) and assert: no invented
   values from the list above, empty states are present and at most 5 words,
   and no `Online`/`Connected` text when the connection is disconnected.
4. **Layout scan.** `scripts/ui-check.mjs` already scans every page at 900,
   1280, 1440 and 1920 px for overlap, horizontal overflow and clipped text.
   Run it if your sandbox allows (app on `VITE_LYSSTACK_API_URL=http://localhost:8000
   npx vite --host localhost --port 3001`; `SCRATCH` set to a temp dir; Hermes
   only allows that origin) and record the report. Stop the server afterwards.
   If it cannot run, say so in the handoff. Do not add dependencies.
5. Manually review each page's component code for the alignment and copy rules
   in `HANDOFF_AGY.md` / the sprint brief: equal-width card grids, shared
   primitives, tokens instead of hex, copy limits (subtitles at most 3 words,
   empty states at most 5 words), and that no page leaves an orphan card in a
   grid row.

## Done means

All five commands from task 1 pass with the new tests included.

## Handoff

Create `HANDOFF_CODEX.md`: commands run with pass/fail, defects found and
fixed, defects found and not fixed (with file and reason), residual risks.
Stop after the handoff.
