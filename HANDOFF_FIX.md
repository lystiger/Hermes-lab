# LysControl M7c Review Fixes Handoff

This document details the fixes applied addressing all findings from `HANDOFF_HARDENER.md` and the M7c review list.

---

## 1. Summary of Changes Per Numbered Item

### Item 1: Unbounded event and error text
- **`src/routes/index.tsx`**: Overview live trace details clamped to 2 lines (`line-clamp-2 break-words`) with the full event detail accessible via native `title={e.detail}` tooltip.
- **`src/features/jobs/JobDetailView.tsx`**: Job inspector trace details clamped to 2 lines (`line-clamp-2 break-words`) with native `title={e.detail}` tooltip.
- **`src/features/jobs/JobRealData.tsx`**:
  - Failure explanation lines clamped to 2 lines (`line-clamp-2`) with `title={line}`.
  - Task errors clamped to 2 lines (`line-clamp-2 break-words`) with `title={describeError(t.error)}`.
  - Run errors clamped to 2 lines (`line-clamp-2 break-words`) with `title={describeError(r.error)}`.
- **`src/components/DataStates.tsx`**:
  - `ErrorState`: Error message and unreachable notice clamped to 2 lines (`line-clamp-2 break-words`) with full message in `title`.
  - `StaleNotice`: Stale error notice clamped to 2 lines (`line-clamp-2 break-words`) with full text in `title`.

### Item 2: Usage duplicates
- **`src/routes/usage.tsx`**:
  - Kept single representation for TOKENS, REQUESTS, SUCCESS RATE, and THROTTLING in the `PageHeader` stat strip (`counts`).
  - Removed the 3 redundant top summary cards (`Tokens`, `Success rate`, `Throttling`) that duplicated the stat strip values.

### Item 3: Queue empty columns
- **`src/features/jobs/MissionBoard.tsx`**:
  - Partitioned columns into active groups (with jobs) and empty groups (0 jobs).
  - Active status groups are rendered in an adaptive CSS grid (`items-stretch`) where column cards stretch to equal height (`h-full`).
  - Empty status groups collapse into a compact horizontal status strip (`aria-label="Empty status groups"`), displaying the status icon, name, and count `0`.

### Item 4: Stat strip
- **`src/components/PageHeader.tsx`**:
  - Reserved stat strip height (`min-h-[58px]`) before data arrives whenever the page defines `counts` (`counts !== undefined`), preventing layout shifts during polling or fetch latency.
  - Value and unit baselines aligned via `flex items-baseline leading-none`.
  - Unified unit styling across all values: units (such as `tok` and `%`) are preserved when value is 0 (removed conditional suppression of unit on zero).

### Item 5: Nested interactive elements
- **`src/routes/queue.tsx`**:
  - In `RecoverableJobs`, replaced outer `<button>` that wrapped `<CopyId>` with `<div role="button" tabIndex={0} ...>` and keyboard handler (`Enter`/`Space`), eliminating nested `<button>` inside `<button>`.
- **`src/components/CopyId.tsx`**:
  - Added `e.stopPropagation()` in copy click handler to ensure clipboard interaction does not trigger row navigation.

### Item 6: Copy limits & freshness
- **`src/routes/usage.tsx`**:
  - Shortened page subtitle from 8 words (`since runtime start (process lifetime, not daily)`) to 3 words (`Capacity and limits`).
  - Moved the measurement window qualification (`since runtime start (process lifetime, not daily)`) to an info tooltip item in `NOT_REPORTED` and a short note above provider cards.
  - Added `StaleNotice` when capacity refresh fails with cached data present.
- **`src/features/jobs/JobRealData.tsx` & `src/features/jobs/JobDetailView.tsx`**:
  - Shortened empty states to <= 5 words:
    - Tasks: `No tasks recorded` (3 words)
    - Runs: `No runs recorded` (3 words)
    - Observations: `No observations recorded` (3 words)
    - Verification: `No verification recorded` (3 words)
    - Job trace: `No events recorded` (3 words)
- **`src/api/hooks.ts` & `src/routes/settings.tsx`**:
  - Updated `useSettings` to return `updatedAt` via `useResource`.
  - Passed `updatedAt` to `PageHeader` in `SettingsRoute`, rendering the live `updated HH:MM:SS` stamp.

### Item 7: Dead CSS
- **`src/styles/globals.css`**:
  - Removed unused `.bg-cyber-grid` declaration.
  - Retained `.clip-hex`, `.clip-armor`, and `.bg-striped-pattern` which have active consumers in the UI.

---

## 2. Guard Tests Added & Updated

### Added Tests
1. **`src/__tests__/no-placeholders.test.ts`**:
   - Scans `src/components`, `src/routes`, `src/features`, `src/stores`, and `src/api/adapters/httpAdapter.ts` (excluding mock adapters and tests).
   - Fails on: `#142`, `VehicleStateStore`, `moveinmate`, `$4.12`, `58%`, `SIMULATED`, `~37 min`, `v0.1.0`, `raise cap`, `alert(`, `Phase 4`, `Not reported by Hermes`.
   - Cleaned up leftover occurrences:
     - `src/api/adapters/httpAdapter.ts`: Removed `(Phase 4)` comment.
     - `src/features/agents/AgentDossier.tsx`: Replaced `Not reported by Hermes` with specific unknown reasons (`Hermes did not report a provider/model/role`).
     - `src/components/NotReported.tsx`: Changed accessible label and header text to `Unreported metrics`.
2. **`src/__tests__/text-clamp.test.tsx`**:
   - Renders `ErrorState`, `StaleNotice`, and `JobFailure` with a 2,000-character string.
   - Asserts clamping via `line-clamp-2` class and reachability of the full 2,000-character text via native `title` attribute.

### Updated Tests (Replacing Pinned Removed Copy)
- **`src/__tests__/m1-truth-routes.test.tsx`**: Updated `Not reported by Hermes` query to `Unreported metrics`.
- **`src/__tests__/m2-widgets.test.tsx`**: Updated empty state copy assertions to `No tasks recorded`, `No runs recorded`, `No observations recorded`.
- **`src/__tests__/m3-readable.test.tsx`**: Updated aggregate success rate check to verify value in stat strip and provider progressbar in card.
- **`src/__tests__/m4b-redesign.test.tsx`**: Updated `Not reported by Hermes` query to `Unreported metrics`, and updated empty Running status expectation to check within `Empty status groups` strip.
- **`src/__tests__/m5-audit-fixes.test.tsx`**: Updated verification empty state check to `No verification recorded`.

---

## 3. Verification Results

All required verification commands pass cleanly with 0 errors and 0 warnings:

1. **`npm run typecheck` (`tsc --noEmit`)**: Exit code 0.
2. **`npm run lint` (`eslint .`)**: Exit code 0 (0 errors, 0 warnings).
3. **`npm test` (`vitest run`)**: Exit code 0 (29 test files passed, 223 tests passed, 100% passing).
4. **`npm run build` (`vite build`)**: Exit code 0 (Production bundle built cleanly).

---

## 4. Unaddressed Items / Out of Scope

- None. All 7 review findings and all required guard tests were implemented and verified.
