# M4b decisions: visible redesign (research §1.1, §2, §5, §6)

Judged by screenshots. Captured at 1600×1000 from this worktree's dev server with `scripts/shoot.mjs`, plus
a copy that adds the agent detail routes (`/agents/claude`, `/agents/codex`, `/agents/gemini`).

Live Hermes state at capture: no jobs, no providers, no deployed seats, three idle agents, one runtime event.
The screens therefore show empty states; the redesign is visible in the layout and the empty states, not in data.

## Screenshots

Before (current state at the start of M4b): `/tmp/claude-1000/m4b/before/`
- `overview.png`, `agents.png`, `queue.png`, `execution.png`, `events.png`, `usage.png`

After (final): `/tmp/claude-1000/m4b/final/`
- `overview.png`, `queue.png`, `agents.png`, `agents_claude.png`, `execution.png`, `events.png`, `usage.png`, `settings.png`
- `agents_codex.png` (`/tmp/claude-1000/m4b/final2/`), `agents_gemini.png` (`/tmp/claude-1000/m4b/after3/`):
  the focal crops after tightening.

## Before and after, by brief item

### 1. Noise rule
- **Before:** Overview showed a "Sprint budget" panel reading "— no budget exposed", a "Queue projection" panel with
  "remaining budget —" and "No projected rows", an empty "Provider usage" panel, and a header with
  "queue eta —" and "budget —". Usage had a run-budget panel that was only "—", an agent context panel of
  "—" rows, and a projection panel. Agents had an allowance panel and an activity panel that said
  "not loaded".
- **After:** those panels are not rendered. A single "Not reported by Hermes:" line lists the unknown-only values;
  each is underlined and shows its reason on hover (`NotReported` component). Overview lists estimated spend,
  sprint budget, queue projection, remaining budget and provider usage; Queue lists time estimates and concurrency
  policy; Usage lists run budget, sprint budget, queue projection, per-agent context and provider usage (when no
  provider has reported); the dossier lists run history, activity feed, provider quota and permission matrix.
- A panel that holds real data keeps its unknowns as "—" (for example the dossier specs, the context meter).

### 2. Agent presence
- **Before:** a 40 px portrait next to a status word in a flat box, and a dossier with a small card crop on a
  mostly empty screen.
- **After:** the roster is a column of presence cards. Each has a square focal portrait (the existing avatar
  files), the name, role, status and the current task Hermes reports, with a 3px accent edge in the agent's
  colour. The dossier has a large art pane (2fr of the content width, at least 560px high) cropped to the face,
  with the agent's accent edge.
- **Crops:** `src/theme/agentArt.ts` holds one config per agent: the avatar and card files and a focal point
  (x, y as fractions of the image) with a zoom. `FocalImage` scales the image about that point. The sheet
  text (names, quotes, profile columns) falls outside the crop. The cutout assets will replace these files
  through the same config.
- Crop settings, verified by eye on the screenshots:
  - Claude: x 0.36, y 0.27, zoom 2.4
  - Codex: x 0.30, y 0.22, zoom 3.0 (first try at 2.1 still showed "VISION" and "EXPRESSION" at the right edge)
  - Gemini: x 0.27, y 0.20, zoom 3.0 (first try at 2.2 still showed profile text)
- Per-agent accents (measured from the art by the lead): claude #CCA27D, codex #7A8ECE, gemini #9686E1,
  hermes #CBA35C. Derived dim tints are `--lys-agent-<name>-dim` (18% `color-mix`).

### 3. Hierarchy
- **Before:** a 46 px top bar held the page title in 14 px, and every label was monospace.
- **After:** `PageHeader` gives each page a display-font title (Outfit, 30 px), a subtitle, and live counts in
  Outfit 28 px with small dim units (for example "0 tok"). Global header keeps only the breadcrumb and the
  connection status.
- Mono is now only for IDs (`CopyId`), timestamps (event time, agent and job start), and code (event JSON).
  Labels, body and values use Plus Jakarta Sans.

### 4. Card system
- **Before:** each panel was an ad-hoc bordered box with its own padding and colour.
- **After:** one `Card` component is used for every panel. It has a chamfered corner (clip-path, 12px outer and
  11px inner, so the hairline follows the cut), a layered surface (surface-1 on the surface-0 page), a
  subtle hairline, and an optional accent edge plus a 12% gradient tint of the accent.
- Contrast of text over that tint is checked below.

### 5. Status as colour and shape
- **Before:** a flat list of queue rows with a tiny state word; priorities always shown as P1 by default.
- **After:** the queue is a mission board with one column per real status. Each column header carries a tone
  colour and a glyph (◆ running, ■ blocked, ○ queued, ✕ failed, ✓ completed, ⊘ cancelled, ? unrecognised), a
  count, and a 3px top stripe. Each job card has a state stripe in its column colour. A priority chip appears
  only when Hermes reports a priority, using P0 red, P1 amber and P2/P3 neutral.
- Failed jobs show "MISSION INTERRUPTED" as text, not colour alone.

### 6. Fill the page, short empty states
- **Before:** dark empty areas below short content; "No jobs returned by Hermes." as bare text.
- **After:**
  - Overview stretches the live trace and the grid to the viewport height. Usage keeps its content at the top.
  - Queue columns keep a 220px minimum body, so the board holds its shape while empty.
  - Empty states are centred and short, with the Hermes emblem (`/agents/hermes.webp`) where it is natural:
    Overview active execution and queue, live trace, Queue board, execution seats, events log.

## Contrast and new pairs

- No new text colour. Text tokens remain the ones in the M4 table (`docs/design/m4-decisions.md`), on the
  surfaces they sit on. `m4-theme.test.ts` recomputes every row, including the new agent accent values.
- The M4 table covers every text token on every surface. The card surface is `--lys-surface-1`, which is in
  the table.
- **Accent tint on cards.** The 12% accent gradient lightens the card's left edge. Worst case, computed over
  `--lys-surface-1`:

  | Tint | Faint text `--lys-text-faint` | Muted text `--lys-text-muted` | Primary text |
  |---|---|---|---|
  | gold #CBA35C | 4.61 | 4.92 | 12.39 |
  | claude #CCA27D | 4.59 | 4.91 | 12.34 |
  | codex #7A8ECE | 4.75 | 5.07 | 12.77 |
  | gemini #9686E1 | 4.73 | 5.05 | 12.71 |
  | success #3FB950 | 4.66 | 4.98 | 12.54 |

  All pass 4.5:1 at the strongest tint.
- The four measured agent colours pass AA as text on every surface (see the M4 table).

## Departures from the research

- **Unit styling (§2.2):** big numbers and small dim units are done in the header counts, but not in every
  value on the screen.
- **Glass and blur (§2.3):** not used; the modal backdrop keeps the blur it already had.
- **Quick-switch keys (§1.1):** the roster uses arrows (from M3), not `1`–`3`.
- **Seat memory and output (§5.3):** not shown; Hermes reports neither. They are on the not-reported line.
- **Agent tool permission matrix (§5.1):** not shown; Hermes reports no permission data.
- **Charts and gauges (§5.5):** usage meters are bars (the only meter the data supports), each with a window label.

## Not done (open for the lead)

- The Settings page is only lightly restyled (title and a sentence changed); the Settings panel grid is M3's
  layout.
- The live trace card on Overview stretches to match the rail. With no events it is a tall, mostly empty card.
  A smaller minimum height would look tighter; I left it so the page fills the viewport.
- Cutout assets will change `agentArt.ts` only. Until then the crops depend on the sheet layout staying the same.
