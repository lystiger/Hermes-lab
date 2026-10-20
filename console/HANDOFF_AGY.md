# LysControl M7 Polish Handoff

## 1. Unified Layout Primitives

We unified the design system across LysControl to enforce a single consistent layout and visual language:

- **`PageHeader` (`src/components/PageHeader.tsx`)**
  - **When to use:** Top of every page route (`/`, `/queue`, `/agents`, `/usage`, `/execution`, `/events`, `/settings`).
  - **Behavior:** Standard page frame containing the title, concise subtitle (<=3 words or single-instance measurement window qualifier), live freshness stamp (`updated HH:MM:SS`), header info tooltip popover (`HeaderNotReported`), and optional actions.
  - **Stat Strip:** Equal-width CSS grid (`grid-flow-col auto-cols-fr`) spanning the full page width with a reserved height (`min-h-[58px]`) to prevent layout shifts during live SSE/polling updates. Metric labels are unified uppercase tracking-wider text, and zero values hide their unit suffix (`0` instead of `0 tok`).

- **`Card` (`src/components/Card.tsx`)**
  - **When to use:** Every container, panel, or modular widget across all pages.
  - **Behavior:** Removed chamfered clip-paths and radial gradient background tints in favor of uniform border radius (`var(--lys-radius-md)` / 4px), subtle hairline border (`bg-lys-subtle` with 1px padding), and clean surface background (`bg-lys-surface-1`). State or agent identity is indicated cleanly by a 3px left accent edge (`accent`) rather than dual border/badge color clutter.

- **`HeaderNotReported` (`src/components/NotReported.tsx`)**
  - **When to use:** In the page header for any metrics or endpoints Hermes does not expose.
  - **Behavior:** Replaced verbose bottom-of-page footers (`Not reported by Hermes: ...`) with an unobtrusive `(i)` info tooltip icon in the header actions area. Preserves full accessible labeling and explanation text for users and automated tests without cluttering visual hierarchy.

- **`CopyId` (`src/components/CopyId.tsx`)**
  - **When to use:** Any identifier (job ID, run ID, event ID, seat ID).
  - **Behavior:** Supports `truncate` with a native `title={value}` tooltip. Replaces mid-word wrapping (`break-all`) with clean ellipsis while preserving one-click clipboard copying.

- **`DataStates` (`src/components/DataStates.tsx`)**
  - **When to use:** Loading, error, stale, and empty states.
  - **Behavior:** Empty states are condensed to concise single phrases (<=5 words, e.g., "No jobs", "No seats", "No events").

---

## 2. Per-Page Changes

### Overview (`/`)
- **Grid:** 12-column layout (`col-span-12 lg:col-span-8` main column and `col-span-12 lg:col-span-4` side rail) with shared card styles, padding, and gaps (`gap-5`).
- **Words Cut:**
  - Removed bottom-of-page "Not reported by Hermes" footer (moved to header tooltip).
  - Removed repetitive "since runtime start" strings from individual cards.
  - Shortened empty states and helper text.
  - Truncated assigned agent lists with full tooltips to eliminate layout overflow.

### Queue (`/queue`)
- **Grid:** Mission board transformed from 6 narrow columns into 3 wide columns at 1280px (`xl:grid-cols-3`); 4-column equal stat strip; `RecoverableJobs` panel collapses to a single line when empty.
- **Words Cut:**
  - Subtitle shortened to "Mission board" (2 words).
  - Removed redundant top bar breadcrumb subtitle.
  - Removed keyboard navigation hint footer ("↑↓ move · Enter opens the job inspector").
  - Removed leftover placeholder sentence "Resume and cancel are not available from this console".
  - Empty columns show a faint dash (`—`) instead of "none".
  - Failure note shortened to uppercase `MISSION INTERRUPTED`.
  - Truncated job IDs and titles with copy button and native tooltip (no mid-word splitting).

### Agents (`/agents`)
- **Grid:** Responsive master-detail layout. Dossier portrait is capped to ~1/3 panel width (`lg:grid-cols-[280px_1fr] xl:grid-cols-[320px_1fr]`, `h-[380px]`), with the specs and context meter panel occupying the remainder.
- **Words Cut:**
  - Subtitle shortened to "Operator inspection" / "Fleet roster".
  - Dispatch button label shortened to 1 word: "Dispatch" (disabled with tooltip explanation).
  - Character sheet button shortened to 2 words: "Character sheet".
  - Removed keyboard navigation footer.
  - Removed placeholder `'no current task reported'`.
  - Empty states shortened to "No agents" / "No agent selected".
  - Added native tooltips to all spec values and role lines.

### Usage (`/usage`)
- **Grid:** Summary meters and provider cards unified onto a single 3-column grid (`grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5`), eliminating 2+1 orphans. Each provider card renders a standard 2x2 grid (`grid-cols-1 sm:grid-cols-2 gap-4`) with 4 fields in identical positions.
- **Words Cut:**
  - Subtitle provides the single measurement qualification: `since runtime start (process lifetime, not daily)` once per page under the title, completely removing the repeated qualifier from all individual meter cards.
  - Removed bottom footer (moved to header tooltip).
  - Shortened empty state to "No provider usage".

### Execution (`/execution`)
- **Grid:** 3 backend cards span the row equally (`grid-cols-1 md:grid-cols-3 gap-5`); deployed seats empty state collapses to a single line.
- **Words Cut:**
  - Subtitle shortened to "Backends and seats" (3 words).
  - Empty deployed seats note shortened to "No deployed seats".
  - Removed bottom footer (moved to header tooltip).

### Events (`/events`)
- **Grid:** Unified category and source filter pills into a single row; clean tabular grid for event rows (`grid-cols-[80px_16px_110px_120px_minmax(0,1fr)_120px]`).
- **Words Cut:**
  - Subtitle shortened to "Live bus buffer" (3 words).
  - One-line event rows with full native tooltips on truncated elements (`title={...}`), expanding JSON details on click.

### Settings (`/settings`)
- Subtitle shortened to "Runtime and presentation" (3 words).

### Top Header Bar (`src/components/Header.tsx`)
- Removed redundant second line breadcrumb subtitle that previously duplicated page subtitles.

---

## 3. Deliberately Preserved

- **Data Truthfulness:** No unbacked or estimated metrics are invented. Fields Hermes does not report remain honest (`—` with explanation tooltip).
- **Interactive Features:** Collapsible sidebar, keyboard shortcuts (arrow navigation, Escape modal close), copy-id buttons, live update timestamps, and disconnected recovery banner.
- **Accessibility:** ARIA roles (`role="log"`, `role="list"`, `role="progressbar"`, `role="region"`), high-contrast states, and reduced-motion CSS animations.
- **API Contracts:** The Hermes API contract, client adapters, and `HermesApi` interface were completely untouched. `src/__tests__/architecture.test.ts` passes cleanly without mock leakage.

---

## 4. Tests and Verification Results

1. **`npm run typecheck` (`tsc --noEmit`)**:
   - Exit code: 0 (No TypeScript errors).
2. **`npm run lint` (`eslint .`)**:
   - Exit code: 0 (0 errors, 0 warnings across all files).
3. **`npm test` (`vitest`)**:
   - 27 test files passed.
   - 219 tests passed (100% passing).
4. **`npm run build` (`vite build`)**:
   - Exit code: 0 (Production bundle built cleanly in ~300ms).
5. **Headless Chromium Layout Scan (`scripts/ui-check.mjs`)**:
   - Tested viewports: 900px, 1280px, 1440px, 1920px across all 7 routes (`overview`, `queue`, `agents`, `execution`, `events`, `usage`, `settings`).
   - Results: **0 issues across all 28 page/width combinations**.
   - Overlaps: 0.
   - Horizontal page overflows: 0.
   - Clipped text without tooltip: 0.

---

## 5. Known Risks

- External tooling or tests matching the removed verbose footer string `"Not reported by Hermes: ..."` at the bottom of pages should query the accessible `HeaderNotReported` component (`aria-label="Not reported by Hermes"`) instead.
