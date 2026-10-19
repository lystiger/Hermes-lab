# Role: BUILDER — LysControl M7 polish (fewer words, aligned cards)

You are the BUILDER. Hermes owns Git orchestration. Do not run git add, git
commit, git merge, git push, git reset, git checkout, or alter Git metadata.
Work only in your assigned worktree (the LysControl repository: React 19,
Vite, Tailwind 4, Zustand, react-router).

First action: run `npm ci`. Then read `docs/console-spec.md` (the rules this
console follows) and `docs/api-audit.md`, and skim `src/components/*`,
`src/routes/*`, `src/features/*`, `src/styles/globals.css`.

## Where things stand

This branch already shows only real Hermes data (no invented metrics), has a
collapsible sidebar, an "updated" stamp, honest loading/error/empty states, and
219 passing tests. Do not undo that. The remaining problem is the one the
operator reported:

> "Make the UI/UX usable and aesthetic. Every word and every card aligned.
> Reduce the amount of words."

The operator has seen it running against the live API. What they see:

1. **Too many words.** The phrase "since runtime start (process lifetime, not
   daily)" repeats on every Usage and Overview card. Every page ends with a
   "Not reported by Hermes: a · b · c" footer. Subtitles are sentences
   ("Mission board · grouped by the status Hermes reports · 1 jobs in the
   latest sample", "counts from the latest 1 jobs (GET /jobs)",
   "Backends and deployed seats from the execution snapshot · loaded
   12:01:56"). Key-hint footers ("↑↓ move · Enter opens the job inspector").
   Empty states are sentences ("No deployed seats. Hermes reports no live
   execution resources right now."). Placeholder-like leftovers: the button
   "dispatch task (unavailable)", "no current task reported", "Resume and
   cancel are not available from this console", "none" in every empty column.
2. **Two header lines say the same thing.** A top bar line ("job queue · latest
   jobs from Hermes") sits above a page title with its own subtitle.
3. **Cards do not share a grid.** Usage shows 3 summary cards, then provider
   cards as 2 + 1 with an orphan; Overview mixes a full-width card, a 3-up
   row and a side rail of different card widths; Execution has 3 backend
   cards that do not span the row. Card paddings, corner shapes (chamfered
   clip-path corners on some, not others), gradients and tinted backgrounds
   vary.
4. **Stat rows are loose.** Big numbers float left in a row that does not use
   the page width and does not line up with the card grid below.
5. **Queue cards truncate badly.** The job id wraps mid-word across three
   lines ("run_20261019_115655_l / yscontrol-m7-usabilit / y"); columns are too
   narrow for the content; six columns for one job.
6. **Agents page** is dominated by a very large portrait; the information
   panel is small by comparison.
7. **Grammar and units:** "1 jobs", "O tok" next to a bare 0, mixed case and
   mixed tracking in labels (some ALL CAPS wide-tracked, some sentence case).

## What to do

### A. One layout system (use it everywhere)
- A single page frame: title row (title, one right-aligned freshness stamp and
  actions), then a stat strip, then content. Remove the top-bar breadcrumb
  line when it only repeats the page subtitle. No page subtitle unless it adds
  information not in the title, max 3 words.
- A stat strip is a CSS grid with equal columns that span the content width;
  every stat is label (small, one case style) over value (one size) with the
  same baseline across stats. Reserve the strip height so live updates do not
  shift the page.
- Content cards sit on a shared 12-column (or equivalent) grid with one gap
  and one padding. Cards in a row have equal height. No orphan cards: choose
  column counts so the row fills (e.g. 3-up, or 2-up, or auto-fit with a
  min width and equal stretch).
- One card style: same radius, border, background. Remove the chamfered
  clip-path corners and gradient tints unless they encode state; if kept, keep
  them on every card. Status is shown by one accent edge or one badge, not
  both.
- Tokens only: spacing scale, one label style, one value style, one mono style
  (ids, times, numbers in tables). Numbers right-aligned in tables, tabular
  figures.

### B. Cut the words
- Put the "since runtime start" qualifier once per page (in the stat strip
  tooltip or one small note under the title), not on every card.
- Delete all "Not reported by Hermes: …" footers; if the list is useful keep
  it as a tooltip on an info icon in the page header.
- Delete keyboard-hint footers (keep the shortcuts working; list them in a
  tooltip or a `?` popover).
- Subtitles: remove or ≤ 3 words. Section titles: 1–3 words.
- Empty states: one line, ≤ 5 words ("No jobs", "No seats", "No events").
  Empty columns on the mission board show nothing but a faint dash.
- Buttons: 1–2 words. Disabled actions stay disabled with a tooltip giving the
  reason; the visible label is just the action ("Dispatch").
- Status words are one word. Pluralise correctly ("1 job").
- Delete helper text that restates the UI.

### C. Fix the specific layouts
- Queue: job card shows a short title and a truncated id with `title` tooltip
  and a copy button (no mid-word wrapping); fewer columns or wider columns so
  cards are readable at 1280 px; the "Recoverable" panel collapses to one line
  when empty.
- Agents: portrait at a sensible fixed size (about one third of the panel
  width, capped), information panel gets the rest.
- Usage: summary cards and provider cards on one grid; provider card shows
  the same four fields in the same positions; no repeated qualifier.
- Execution: backend cards fill the row equally; empty sections one line.
- Events: one filter row if it fits (sources in a dropdown or a second row only
  when needed); one-line rows with the payload on expand.
- Overview: one grid; the side rail uses the same card style and widths.

### D. Keep it honest and usable
- Do not add any value that Hermes does not report. Unknown stays "—".
- Keep: sidebar collapse, keyboard navigation, copy-id, freshness stamps,
  disconnected banner, reduced-motion support.
- No horizontal overflow and no clipped or overlapping text at 900, 1280,
  1440 and 1920 px. `node scripts/ui-check.mjs <outdir> <baseUrl> <waitMs>`
  runs the layout scan and screenshots (set `SCRATCH` to a temp dir). Start the
  app with `VITE_LYSSTACK_API_URL=http://localhost:8000 npx vite --host
  localhost --port 3001` (Hermes allows that origin; a different port gets a
  CORS error). Stop the server when you finish. If the check cannot run in
  your sandbox, say so in the handoff and rely on the tests.

## Constraints

- Do not change the Hermes API contract or the `HermesApi` interface.
- `src/__tests__/architecture.test.ts` must keep passing (no `api/mock`
  imports from UI code).
- Update tests whose assertions pin removed copy; do not delete a test
  without replacing its intent.
- No new runtime dependencies. Keep routes and URLs.

## Done means

`npm run typecheck`, `npm run lint`, `npm test`, `npm run build` all pass.

## Handoff

Create `HANDOFF_AGY.md`: the layout primitives you added or reused and when to
use each, per-page what changed (words removed, grid used), anything you chose
not to change and why, tests run, known risks. Stop after the handoff.
