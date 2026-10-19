# M7d fixes

## Defect 1 — real job statuses

- `src/api/types.ts`: added CREATED, EXECUTING, WAITING_FOR_CAPACITY to JobStatus.
- `src/api/adapters/httpAdapter.ts`: JOB_STATUS_GROUPS is the single classification source. Running includes EXECUTING, PLANNING, VERIFYING, REPAIRING, RUNNING and PREPARING; queued includes CREATED, QUEUED, CLAIMED and WAITING_FOR_CAPACITY. BLOCKED and each terminal status retain distinct groups. Telemetry and active pipeline selection use these definitions. Failed jobs without completion timestamps still produce an unknown 24-hour count.
- `src/features/jobs/MissionBoard.tsx`: board status membership derives from the shared groups; unknown statuses retain raw text in Other columns.
- `src/components/Sidebar.tsx`: imports the terminal statuses derived from the shared groups for its nonterminal queue badge.
- Queue and Overview stat strips already consume adapter telemetry; Overview's ActiveExecutionCard already consumes ACTIVE_JOB_STATUSES. They now receive the corrected classifications without route edits.
- Tests added in `src/__tests__/m7d-fixes.test.tsx`: 14 parameterized cases covering every real and legacy status, matching telemetry and terminal membership; unknown raw status preservation; EXECUTING rendered in Overview's active execution card.

## Defect 2 — execution ID overlap

- `src/features/execution/ExecutionResourceCard.tsx`: job and task IDs occupy separate truncated rows, each with its full ID in a title tooltip. The container can shrink with min-w-0. Existing equal-width responsive grid columns remain intact.
- Test added in `src/__tests__/m7d-fixes.test.tsx`: long job/task IDs retain full tooltips and separate truncated rows within a shrinking column container.
- Browser geometry at 1280 px was not measured: the allowed commands exclude running the UI scan, and servers were prohibited. The DOM test verifies structure, not rendered pixel geometry.

## Defect 3 — empty state

- `src/features/jobs/JobDetailView.tsx`: changed the no-job/no-error message to “No job loaded” (3 words).
- No dedicated test added for this static copy change.

## Validation

- Ran `npm ci` first: passed.
- `npm run typecheck`: passed.
- `npm run lint`: passed.
- `npm test -- --run`: passed, 30 files / 240 tests (17 new tests).
- `npm run build`: passed.
- Initial validation caught fixture type mismatches and an Overview assertion made before loading completed; corrected the tests and reran all required checks successfully.
- No Git commands or metadata changes performed. No servers started.

All three requested source fixes are complete. Browser layout scan remains unrun for the command restrictions above.
