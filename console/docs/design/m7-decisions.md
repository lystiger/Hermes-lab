# M7 decisions: usability (D-018, milestone 1)

Scope: text that never clips silently, one icon set, a collapsible sidebar, one scroll container per page,
and live data sync. The Agents data model is unchanged (M6 rebuilds it).

## Before and after: `scripts/ui-check.mjs`

Run: `SCRATCH=<dir> node scripts/ui-check.mjs <out> http://localhost:3001 5000` against this worktree.
The script checks overlapping text, horizontal page overflow, and text clipped without a tooltip, on
7 pages at 4 widths (28 combinations).

| Width | Before (issues) | After (issues) |
|---|---|---|
| 900 px | 286 | 0 |
| 1280 px | 184 | 0 |
| 1440 px | 147 | 0 |
| 1920 px | 140 | 0 |
| **Total** | **757** | **0** |

Per page, before → after (all widths summed by page):

| Page | 900 | 1280 | 1440 | 1920 |
|---|---|---|---|---|
| Overview | 15 → 0 | 9 → 0 | 4 → 0 | 1 → 0 |
| Queue | 0 → 0 | 0 → 0 | 0 → 0 | 0 → 0 |
| Agents | 0 → 0 | 3 → 0 | 0 → 0 | 0 → 0 |
| Execution | 86 → 0 | 50 → 0 | 43 → 0 | 43 → 0 |
| Events | 185 → 0 | 122 → 0 | 100 → 0 | 96 → 0 |
| Usage | 0 → 0 | 0 → 0 | 0 → 0 | 0 → 0 |
| Settings | 0 → 0 | 0 → 0 | 0 → 0 | 0 → 0 |

Every before-issue was `clipped-without-tooltip`: `truncate` on live event, run and seat text that
could not fit its fixed-width column. No overlaps or horizontal overflow were found before or after.

The script's "nested scroll containers" count is 1 on every page that overflows. The count is taken
from the page's `lys-scroll` container; no other element scrolls (checked with a separate probe).

## Decisions by item

### 1. Text never clips silently
- Fixed-width columns on live rows were replaced by wrapping layouts. Event and trace rows are a
  two-line entry: the source and kind on the first line, the detail below, and the job and run IDs in
  a wrapping mono line. IDs use `break-all`. Execution timeline rows wrap the detail and move IDs to
  their own line below `md`.
- `truncate` is gone from the live pages. The few that remain (sidebar labels, and two unused legacy
  components) keep a `title` showing the full text, which the brief allows.

### 2. One icon set
- All icons are `lucide-react` 1.33 through one wrapper, `src/components/Icon.tsx`: 14px, 2px stroke.
  Decorative icons are hidden from assistive tech; a labelled icon is an image with an accessible name.
- Replaced: the mission board's status glyphs (◆ ■ ○ ✕ ✓ ⊘) with Activity, OctagonAlert, Clock, X,
  Check and CircleSlash; the job phase marks (✓ ✕ ● ○) with Check, X, CircleDot and Circle; the
  artifact icons (⎇ 🗎 📊 📋 ≡ ◈) with GitCommit, FileText, ChartColumn, ClipboardList, List and Layers;
  the message badges (⚙ TOOL, ↳ reply) with Cog and CornerDownRight; the close marks with X.
- Kept as typography, per the brief: · — … → and the keyboard hints (↑ ↓).
- Icon-only controls each have an accessible name and a tooltip: the sidebar toggle, the collapsed
  navigation links, the reply cancel, and the artifact close.

### 3. Sidebar
- Button collapse and expand; the `[` key toggles it (ignored while typing in a field).
- The choice is remembered in `localStorage` (`lys.sidebar.collapsed`). Every access is in a try/catch,
  so blocked storage only loses the memory, not the control.
- Below 1100 px the sidebar starts collapsed. The user can open it for the current view.
- Collapsed, the sidebar shows icons only, each with an accessible name and a tooltip. The main area
  reflows to the remaining width; nothing is hidden under the sidebar.

### 4. Scrolling
- One scroll container per page: the `lys-scroll` element in `Layout`. The body does not scroll, so
  there are no double scrollbars.
- Page headers are sticky inside that container.
- Smooth scrolling is on only under `prefers-reduced-motion: no-preference`.
- No layout jumps on live events. On Events, when the operator has scrolled away from the top, the
  list is frozen to what they were reading and new events are counted in a pill ("N new events · back
  to newest"). At the top, new events appear at once.

### 5. Live data sync
- Every page reads the store and hooks that update from the SSE stream and the execution snapshot. No
  page needs a manual refresh.
- Each data panel shows "updated HH:MM:SS" (page headers, Overview panels, agent dossier, job lists,
  execution snapshot, Settings backends). Stale and disconnected states use the existing components:
  the connection banner, the stale notice with retry, and the "not streaming" state on Events.
- **Bug found while verifying this item.** The keyed resource hook from M5 discarded any response that
  was not the most recent request. Live job and agent events restart loads many times a second, so on a
  busy runner the Overview's agent, job and telemetry loads were superseded before they could finish and
  the panels stayed on "Loading" (seen on the live API). The fix applies a response when it is newer
  than the last one applied, which still blocks an older response overwriting a newer one. A regression
  test bumps the version several times and resolves the requests out of order.

## Tests
- `src/__tests__/m7-usability.test.tsx`:
  - sidebar state: collapse, memory, reload, the blocked-storage case, the `[` key and the typing exception,
    narrow-window auto-collapse and open-for-view;
  - icon labels: labelled and decorative icons, and every collapsed navigation link;
  - the new-events pill: freeze while scrolled, the arrival count, release on "back to newest", and
    immediate display at the top;
  - the starvation regression for the request guard.
- Existing tests updated where the old glyph text was asserted (the messaging badges now carry icons).

## Departures and open items
- The Settings page is only partly restyled (its panel grid is M3's layout).
- `AgentLaneCard` and `ToolCallItem` have no page on them; they are kept for tests and still use
  truncation with tooltips.
- The Overview live trace stretches to the rail's height, which leaves space when few events exist.
- Mock fixtures still contain the old glyphs as data (`api/mock`); they are not rendered as icons.

## Screenshots
Written by the UI check and the probes, under the scratch directory used for the run:
- Before (ui-check): `/tmp/claude-1000/m7/before/<width>/<page>.png`
- After (ui-check, final code): `/tmp/claude-1000/m7/final/<width>/<page>.png`
- Narrow sidebar: `/tmp/claude-1000/m7/after2/900/overview.png` and `/900/events.png`
- Wrapped live rows: `/tmp/claude-1000/m7/after2/1280/execution.png`
- Live Overview after the sync fix: `/tmp/claude-1000/m7/probe4/overview.png`
