# LysControl M7 hardener verification

Status: checks pass; hardening objective remains incomplete. No source files or tests were changed. The operator's explicit rule, “Never modify source files in verifier role,” prevented implementing the requested fixes. This handoff is the only authored change. No Git commands were run or Git metadata intentionally changed.

Read HANDOFF_AGY.md first, then reviewed current source against docs/console-spec.md. Baseline diff review was not performed: the command allowlist excludes git diff, and no baseline patch was supplied. Builder handoff claims were treated as prior reports, not fresh evidence.

## Priority findings and reproduction

1. **Unbounded event and error text remains.** Overview renders e.detail with break-words and no clamp or title (src/routes/index.tsx:121). Inspector trace does the same (src/features/jobs/JobDetailView.tsx:244). Failure explanation lines have no clamp/title (src/features/jobs/JobRealData.tsx:34); task and run errors are unbounded at lines 101 and 125. Shared ErrorState and StaleNotice also render unbounded messages (src/components/DataStates.tsx:45,71). Reproduce against Hermes data containing a multi-paragraph failed-task prompt/error, then inspect Overview and the job inspector. Expected: at most two list lines, full text accessible by tooltip or expansion. Current source imposes no line bound. Events rows already have one-line truncation and a full-detail title (src/routes/events.tsx:154), plus expandable JSON. Queue failure note is static MISSION INTERRUPTED; blockedReason already truncates with a title (MissionBoard.tsx:160-165).
2. **Usage duplicates three metrics.** src/routes/usage.tsx:28-31 puts tokens, success rate and throttling in the strip; lines 56-91 render them again as cards. Reproduce by opening /usage with any successful capacity response. Keep one representation; no correction made.
3. **Empty Queue columns retain grid space.** src/features/jobs/MissionBoard.tsx:60,75-95 maps all six groups into the same three-column grid and gives empty bodies h-16. Reproduce with one running job and no other statuses at 1280px or wider. Empty groups retain equal column width. Collapse empty groups into a compact strip; no correction made.
4. **Mixed-unit baseline needs browser verification.** PageHeader.tsx:39 aligns cells at their bottoms; line 43 aligns the value and unit only within each individual cell. Units disappear for zero values (line 50), making formatting inconsistent. Reproduce with plain counts beside nonzero percentages, then update the percentage to zero. The reported visual baseline defect was not independently reproduced because browser initialization failed.

## Checklist disposition

1. **Truth: partial verification.** Default client is HTTP localhost:8000; mock mode requires explicit VITE_LYSCONTROL_MOCK=1 and Layout shows a persistent banner. Searches for the listed demo strings found fixtures/tests/mock adapter and the explicitly gated mock clock, rather than newly identified live UI placeholders. Truth, adapter and architecture tests passed. This is not an exhaustive live API audit or a baseline change audit.
2. **Alignment: failures remain.** Duplicate Usage metrics, empty Queue grid space and mixed-unit concerns above. MissionBoard uses items-start, so columns do not enforce equal heights. Shared primitives and theme colors exist; no raw hex found in the inspected components/features. Runtime equal-height and baseline verification remains outstanding.
3. **Copy: failures remain.** Usage subtitle is eight words (usage.tsx:40), exceeding three; job inspector empty states exceed five words (JobRealData.tsx:86,116,141,172). Mission board correctly pluralizes 1 job. No corrections made. Runtime-start qualifier is single-instance in Usage source inspected.
4. **Layout safety: unverified in browser.** Overview and inspector long text risks confirmed by source. PageHeader conditionally adds the strip only when counts become available (PageHeader.tsx:38), so its minimum height does not reserve space before data arrives. This remains a layout-shift risk. Shared Layout has one primary vertical scroll container. No fresh evidence for the four required viewport widths.
5. **Sidebar and shortcuts: automated checks pass.** Existing m7-usability tests cover button toggle, remembered choice, [ keyboard toggle with editable-field exclusion, narrow auto-collapse, blocked localStorage, and accessible collapsed navigation. Source still installs shortcut handlers. No changes made.
6. **States: partial verification.** Shared loading/error/stale/freshness components and global connection banner remain. Existing truth and stale-state tests pass. Usage renders its error only when capacity is absent (usage.tsx:52), so a failed refresh with cached capacity has no local stale/error notice. Settings does not pass updatedAt to PageHeader (settings.tsx:27). No claim of complete loading/error/empty/disconnected coverage on every page.
7. **Accessibility: automated coverage passes; rendered audit incomplete.** Existing theme tests check text-token contrast against surfaces, visible focus and reduced-motion rules; sidebar tests check accessible labels. Actual opacity-modified text, all interactive elements, and rendered contrast were not exhaustively audited. Queue recoverable rows wrap CopyId inside a button (queue.tsx:115-116); inspect for nested button semantics because CopyId is interactive.
8. **Code quality: lint clean; cleanup outstanding.** No existing lint warning reproduced. bg-cyber-grid has no usage found outside its declaration (globals.css:237). The chamfer token remains declared (globals.css:102), with a test asserting its presence, but no runtime use found. clip-hex, clip-armor and bg-striped-pattern still have consumers and should not be removed indiscriminately. Architecture suite passed. No cleanup performed under verifier restriction.

## Commands and results

- npm ci: exit 0; 228 packages installed.
- npm run typecheck: exit 0; no diagnostics.
- npm run lint: exit 0; no errors or warnings emitted.
- npm test: exit 0; Test Files 27 passed (27); Tests 219 passed (219); duration 6.78s. Includes architecture.test.ts.
- npm run build: exit 0; production build completed in 863ms.
- node scripts/ui-check.mjs /tmp/lyscontrol-hardener-ui: exit 1, before page navigation. Exact failure:

```text
scripts/ui-check.mjs:17
const ws = new WebSocket(target.webSocketDebuggerUrl);
                                ^

TypeError: Cannot read properties of undefined (reading 'webSocketDebuggerUrl')
    at file:///home/lystiger/hermes-worktrees/lyscontrol-m7b/hardener/scripts/ui-check.mjs:17:33

Node.js v26.7.0
```

The script obtained no Chromium debugging target. Root cause was not established. No layout report was produced. No app server was started: its launch command is outside the strict shell allowlist. The scan also lacked a confirmed running app/API, so it would require those prerequisites even after browser startup is repaired. No server was left running by this verification. Browser/profile cleanup on the script's exceptional path was not verified.

## Remaining risks

Green checks do not validate the four reported visual defects. All source fixes, baseline review, live-data long-text reproduction, responsive browser audit, and rendered accessibility audit remain outstanding. The previous handoff's zero-issue browser claim was not reproduced. No dependencies, API contracts, or test assertions were edited.
