# Role: HARDENER — LysControl M7

You are the HARDENER. Hermes owns Git orchestration. Do not run git add,
commit, merge, push, reset, checkout, or alter Git metadata. Work only in
your assigned worktree. The builder's work and `HANDOFF_AGY.md` are already in
your worktree. Read the handoff first, then review the diff against the
baseline.

## Objective

Review and fix the builder's LysControl redesign. Do not redesign again;
correct, tighten and finish. The operator asked for: no placeholder data,
usable and good looking UI, every word and card aligned, fewer words.

## Tool rules (a denied command fails the whole phase)

Your shell is already in your worktree. Never `cd`, never chain commands with
`;` or `&&` that change directory, and never run inline scripts (`python3 -`,
heredocs, `node -e`, `sed -i` pipelines) to edit files. Edit files only with
the Edit and Write tools. Run only `npm ci`, `npm run typecheck`,
`npm run lint`, `npm test`, `npm run build`, plain `grep`/`ls`, and
`node scripts/ui-check.mjs`. Do not run git commands that modify state.

## Known defects from the builder review (fix these first)

The builder's commit passes typecheck, lint, tests and build. A review of its
running pages found:

1. **Unbounded event text.** An event with a very long `detail` (a failed task
   whose error contains a full prompt) renders as a huge block in the
   Overview live trace and pushes every other card off screen. Clamp event
   detail to 2 lines in lists, with the full text on expand or in a `title`
   tooltip. Apply the same clamp wherever event or error text is listed
   (Events rows, job inspector error lines, queue card failure note).
2. **Duplicated numbers on Usage.** The stat strip and the three cards below
   it show the same three values (tokens, success rate, throttling). Keep
   one. Prefer the strip and drop the duplicate cards, or keep cards with
   their meters and drop those values from the strip.
3. **Queue wasted space.** The mission board shows six columns in a 3 x 2
   grid, and empty columns take as much room as full ones. Collapse empty
   columns into a compact strip (name and count) and give the space to
   columns with jobs.
4. **Stat strip baselines.** Values with units ("100 %") sit higher than plain
   numbers in the same strip. Align baselines and use one unit style.

## Checklist (fix what fails)

1. **Truth.** The branch shows only real Hermes data (see
   `docs/console-spec.md`). Confirm the polish did not reintroduce any
   hard-coded demo value (`#142`, `Redis`, `moveinmate`, `$4.12`, `58%`,
   `SIMULATED`, `~37 min`, `v0.1.0`, `10:42`, `raise cap`) or any number that
   is not from an API response. Unknown stays `—`.
2. **Alignment.** Within each page, cards in a row have equal width and
   height; labels and values share baselines; paddings, gaps, radii and borders
   come from the shared primitives and tokens, not one-off classes. No raw hex
   colors in components.
3. **Copy.** Page subtitles are gone or at most 3 words; section titles 1 to 3
   words; empty states one line of at most 5 words; no "Not reported by
   Hermes" footers, no key-hint footers, the "since runtime start" qualifier
   appears once per page, correct plurals ("1 job"), one label case style.
4. **Layout safety at 1280, 1440, 1920 and 900 px.** No overlapping or clipped
   text, no horizontal overflow, one scroll container per page, no layout jump
   when live data arrives. Long text truncates with a `title` tooltip.
5. **Sidebar and shortcuts.** Still collapse/expand by button and keyboard,
   state remembered, auto-collapse on narrow windows; removed hint footers
   did not remove the shortcuts themselves.
6. **States.** Every page has loading, empty, error and disconnected states
   that are short and honest. Header shows connection and "updated hh:mm:ss".
7. **Accessibility.** Visible focus rings, interactive cards are `button` or
   `a`, contrast of muted text on the dark background is at least 4.5:1,
   `prefers-reduced-motion` respected.
8. **Code quality.** Remove components and CSS orphaned by the polish (for
   example chamfer/gradient helpers nothing uses), unused exports, and fix the
   one existing lint warning if it is trivial. Keep `architecture.test.ts`
   passing. If `node scripts/ui-check.mjs` can run in your sandbox (app on
   `VITE_LYSSTACK_API_URL=http://localhost:8000 npx vite --host localhost
   --port 3001`, `SCRATCH` set to a temp dir), run it and fix what it reports;
   stop the server afterwards.

## Constraints

- Do not change the Hermes API contract. No new runtime dependency.
- Do not delete tests to make them pass; update assertions to the new honest
  behavior.

## Done means

`npm run typecheck`, `npm run lint`, `npm test`, `npm run build` all pass.

## Handoff

Create `HANDOFF_HARDENER.md`: what you found and fixed per checklist item,
anything left unfixed and why, tests run, known risks. Stop after the handoff.
