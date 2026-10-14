# M4 decisions: theme and motion (research §2, §3, §6, §7)

Source of the tokens: `docs/design/mihoyo-ui-research.md` §6. Visual decisions follow §2 (colour, typography,
depth), §3 (motion), §6 (tokens) and §7 (accessibility). Where the console departs from the research, the
departure and its reason are listed below each area. Nothing here changes data behaviour.

Single source of truth: `src/styles/globals.css` declares every token. The Tailwind theme (`@theme`) exposes
every colour as a utility (`text-lys-muted`, `bg-lys-surface-2`, `border-lys-subtle`). Inline styles use
`var(--lys-…)`. `src/__tests__/m4-theme.test.ts` checks the declared values, the theme exposure, and that no
component contains a hard-coded hex or `rgba()` colour.

## 1. Colour tokens (§2.1, §6.1–§6.4)

| Group | Tokens | Research |
|---|---|---|
| Surfaces | `--lys-bg-base` #08090B, `--lys-surface-0` #0C0E12, `--lys-surface-1` #12151B, `--lys-surface-2` #181D25, `--lys-surface-interactive` #202632 | §6.1 values, used as given |
| Borders | `--lys-border-subtle` #1C222C, `--lys-border-default` #28303E, `--lys-border-strong` #3D485C | §6.2 (`highlight` renamed `strong`) |
| Text | `--lys-text-primary` #E6E9ED, `--lys-text-secondary` #B7BEC7, `--lys-text-muted` #8C949F, `--lys-text-faint` #868F9B | §2.1 neutral tiers |
| Status | `--lys-status-success` #3FB950, `--lys-status-warning` #E3A008, `--lys-status-danger` #F5626A, `--lys-status-info` #58A6FF | §6.4 values; danger lightened (see departures) |
| Accents | `--lys-accent-gold` #CBA35C, `--lys-accent-gold-hover` #E8CE9B, `--lys-accent-sky` #7FB3D5, `--lys-accent-violet` #A78BFA | §2.1 tiers, §6.3 gold |
| Agents | `--lys-agent-claude` #CCA27D, `--lys-agent-codex` #7A8ECE, `--lys-agent-gemini` #9686E1, `--lys-agent-hermes` #CBA35C | §6.3, one variable per agent |
| Ink | `--lys-ink` #000000 | overlays and shadows only |

**Per-agent accents.** Each agent has exactly one variable. `src/theme/agents.ts` is the one place that maps
agent identity to a variable, and `actorAccent()` applies it before any backend-supplied colour, so the lead's
palette applies to real data as well as mocks. Gemini uses `--lys-agent-gemini`; the `agy` id maps to the same
variable. The lead replaces the four hex values in `globals.css` and nothing else.

**Departures from §6 colour values**
- `--lys-status-danger` is #F5626A, not #F2555A. The original value reached 4.49:1 on the interactive surface,
  just below AA; the lighter value reaches 4.94:1 there and stays recognisably red.
- `--lys-text-faint` is #868F9B, not the old #5C646E. The old dim label colour reached 3.3:1 on the surfaces, which
  fails AA for text. It is the only text colour that changes role; labels keep their size and case to stay
  distinct from `muted`.
- The old palette was mapped token by token (nearest colour in the same role: text, surface, border). Small
  visual shifts follow from that. Pure text and surface tokens are taken from §6 directly.
- Shadows and glass: `--lys-surface-glass` and the card shadows are declared for the theme but not applied.
  §2.3 blur panels are left out for readability (research §4 says glow and blur do not transfer to a
  productivity tool); the only blur is the modal backdrop, which already existed.

## 2. Contrast (§7.1)

Every text token on every surface the console uses is recorded below. The ratios are WCAG 2.1 relative
luminance ratios computed from the token values; each row must be at least 4.5:1. `m4-theme.test.ts` recomputes
them from `globals.css` and fails if a value changes without this table changing.

§7.1 asks for 7.2:1 for primary text on `surface-1`. Primary text is 15.01:1 there, so it passes.

Not covered here: non-text contrast (3:1 for meter tracks, borders and icons, §7.1). Meter tracks and
dashed borders are decorative and carry their value as text. A full non-text audit is left for M5.

| Foreground | Hex | Background | Hex | Ratio | Result |
|---|---|---|---|---|---|
| --lys-text-primary | #E6E9ED | --lys-bg-base | #08090B | 16.36 | AA pass |
| --lys-text-primary | #E6E9ED | --lys-surface-0 | #0C0E12 | 15.86 | AA pass |
| --lys-text-primary | #E6E9ED | --lys-surface-1 | #12151B | 15.01 | AA pass |
| --lys-text-primary | #E6E9ED | --lys-surface-2 | #181D25 | 13.89 | AA pass |
| --lys-text-primary | #E6E9ED | --lys-surface-interactive | #202632 | 12.45 | AA pass |
| --lys-text-secondary | #B7BEC7 | --lys-bg-base | #08090B | 10.63 | AA pass |
| --lys-text-secondary | #B7BEC7 | --lys-surface-0 | #0C0E12 | 10.31 | AA pass |
| --lys-text-secondary | #B7BEC7 | --lys-surface-1 | #12151B | 9.75 | AA pass |
| --lys-text-secondary | #B7BEC7 | --lys-surface-2 | #181D25 | 9.03 | AA pass |
| --lys-text-secondary | #B7BEC7 | --lys-surface-interactive | #202632 | 8.09 | AA pass |
| --lys-text-muted | #8C949F | --lys-bg-base | #08090B | 6.50 | AA pass |
| --lys-text-muted | #8C949F | --lys-surface-0 | #0C0E12 | 6.30 | AA pass |
| --lys-text-muted | #8C949F | --lys-surface-1 | #12151B | 5.96 | AA pass |
| --lys-text-muted | #8C949F | --lys-surface-2 | #181D25 | 5.52 | AA pass |
| --lys-text-muted | #8C949F | --lys-surface-interactive | #202632 | 4.95 | AA pass |
| --lys-text-faint | #868F9B | --lys-bg-base | #08090B | 6.09 | AA pass |
| --lys-text-faint | #868F9B | --lys-surface-0 | #0C0E12 | 5.90 | AA pass |
| --lys-text-faint | #868F9B | --lys-surface-1 | #12151B | 5.58 | AA pass |
| --lys-text-faint | #868F9B | --lys-surface-2 | #181D25 | 5.17 | AA pass |
| --lys-text-faint | #868F9B | --lys-surface-interactive | #202632 | 4.63 | AA pass |
| --lys-status-success | #3FB950 | --lys-bg-base | #08090B | 7.84 | AA pass |
| --lys-status-success | #3FB950 | --lys-surface-0 | #0C0E12 | 7.60 | AA pass |
| --lys-status-success | #3FB950 | --lys-surface-1 | #12151B | 7.20 | AA pass |
| --lys-status-success | #3FB950 | --lys-surface-2 | #181D25 | 6.66 | AA pass |
| --lys-status-success | #3FB950 | --lys-surface-interactive | #202632 | 5.97 | AA pass |
| --lys-status-warning | #E3A008 | --lys-bg-base | #08090B | 8.82 | AA pass |
| --lys-status-warning | #E3A008 | --lys-surface-0 | #0C0E12 | 8.55 | AA pass |
| --lys-status-warning | #E3A008 | --lys-surface-1 | #12151B | 8.09 | AA pass |
| --lys-status-warning | #E3A008 | --lys-surface-2 | #181D25 | 7.49 | AA pass |
| --lys-status-warning | #E3A008 | --lys-surface-interactive | #202632 | 6.71 | AA pass |
| --lys-status-danger | #F5626A | --lys-bg-base | #08090B | 6.49 | AA pass |
| --lys-status-danger | #F5626A | --lys-surface-0 | #0C0E12 | 6.29 | AA pass |
| --lys-status-danger | #F5626A | --lys-surface-1 | #12151B | 5.95 | AA pass |
| --lys-status-danger | #F5626A | --lys-surface-2 | #181D25 | 5.51 | AA pass |
| --lys-status-danger | #F5626A | --lys-surface-interactive | #202632 | 4.94 | AA pass |
| --lys-status-info | #58A6FF | --lys-bg-base | #08090B | 7.89 | AA pass |
| --lys-status-info | #58A6FF | --lys-surface-0 | #0C0E12 | 7.65 | AA pass |
| --lys-status-info | #58A6FF | --lys-surface-1 | #12151B | 7.24 | AA pass |
| --lys-status-info | #58A6FF | --lys-surface-2 | #181D25 | 6.70 | AA pass |
| --lys-status-info | #58A6FF | --lys-surface-interactive | #202632 | 6.00 | AA pass |
| --lys-accent-gold | #CBA35C | --lys-bg-base | #08090B | 8.47 | AA pass |
| --lys-accent-gold | #CBA35C | --lys-surface-0 | #0C0E12 | 8.22 | AA pass |
| --lys-accent-gold | #CBA35C | --lys-surface-1 | #12151B | 7.78 | AA pass |
| --lys-accent-gold | #CBA35C | --lys-surface-2 | #181D25 | 7.20 | AA pass |
| --lys-accent-gold | #CBA35C | --lys-surface-interactive | #202632 | 6.45 | AA pass |
| --lys-accent-gold-hover | #E8CE9B | --lys-bg-base | #08090B | 13.03 | AA pass |
| --lys-accent-gold-hover | #E8CE9B | --lys-surface-0 | #0C0E12 | 12.63 | AA pass |
| --lys-accent-gold-hover | #E8CE9B | --lys-surface-1 | #12151B | 11.95 | AA pass |
| --lys-accent-gold-hover | #E8CE9B | --lys-surface-2 | #181D25 | 11.06 | AA pass |
| --lys-accent-gold-hover | #E8CE9B | --lys-surface-interactive | #202632 | 9.92 | AA pass |
| --lys-accent-sky | #7FB3D5 | --lys-bg-base | #08090B | 8.83 | AA pass |
| --lys-accent-sky | #7FB3D5 | --lys-surface-0 | #0C0E12 | 8.56 | AA pass |
| --lys-accent-sky | #7FB3D5 | --lys-surface-1 | #12151B | 8.11 | AA pass |
| --lys-accent-sky | #7FB3D5 | --lys-surface-2 | #181D25 | 7.50 | AA pass |
| --lys-accent-sky | #7FB3D5 | --lys-surface-interactive | #202632 | 6.72 | AA pass |
| --lys-accent-violet | #A78BFA | --lys-bg-base | #08090B | 7.32 | AA pass |
| --lys-accent-violet | #A78BFA | --lys-surface-0 | #0C0E12 | 7.10 | AA pass |
| --lys-accent-violet | #A78BFA | --lys-surface-1 | #12151B | 6.72 | AA pass |
| --lys-accent-violet | #A78BFA | --lys-surface-2 | #181D25 | 6.22 | AA pass |
| --lys-accent-violet | #A78BFA | --lys-surface-interactive | #202632 | 5.57 | AA pass |
| --lys-agent-claude | #CCA27D | --lys-bg-base | #08090B | 8.57 | AA pass |
| --lys-agent-claude | #CCA27D | --lys-surface-0 | #0C0E12 | 8.31 | AA pass |
| --lys-agent-claude | #CCA27D | --lys-surface-1 | #12151B | 7.86 | AA pass |
| --lys-agent-claude | #CCA27D | --lys-surface-2 | #181D25 | 7.28 | AA pass |
| --lys-agent-claude | #CCA27D | --lys-surface-interactive | #202632 | 6.52 | AA pass |
| --lys-agent-codex | #7A8ECE | --lys-bg-base | #08090B | 6.25 | AA pass |
| --lys-agent-codex | #7A8ECE | --lys-surface-0 | #0C0E12 | 6.06 | AA pass |
| --lys-agent-codex | #7A8ECE | --lys-surface-1 | #12151B | 5.73 | AA pass |
| --lys-agent-codex | #7A8ECE | --lys-surface-2 | #181D25 | 5.31 | AA pass |
| --lys-agent-codex | #7A8ECE | --lys-surface-interactive | #202632 | 4.76 | AA pass |
| --lys-agent-gemini | #9686E1 | --lys-bg-base | #08090B | 6.44 | AA pass |
| --lys-agent-gemini | #9686E1 | --lys-surface-0 | #0C0E12 | 6.25 | AA pass |
| --lys-agent-gemini | #9686E1 | --lys-surface-1 | #12151B | 5.91 | AA pass |
| --lys-agent-gemini | #9686E1 | --lys-surface-2 | #181D25 | 5.47 | AA pass |
| --lys-agent-gemini | #9686E1 | --lys-surface-interactive | #202632 | 4.91 | AA pass |
| --lys-agent-hermes | #CBA35C | --lys-bg-base | #08090B | 8.47 | AA pass |
| --lys-agent-hermes | #CBA35C | --lys-surface-0 | #0C0E12 | 8.22 | AA pass |
| --lys-agent-hermes | #CBA35C | --lys-surface-1 | #12151B | 7.78 | AA pass |
| --lys-agent-hermes | #CBA35C | --lys-surface-2 | #181D25 | 7.20 | AA pass |
| --lys-agent-hermes | #CBA35C | --lys-surface-interactive | #202632 | 6.45 | AA pass |

## 3. Typography (§2.2, §6.5)

- **Families.** Outfit for display (`h1`–`h3`), Plus Jakarta Sans for body (`font-sans`), JetBrains Mono for
  data (`font-mono-code`). All three are OFL and bundled through `@fontsource`, so the console makes no
  request to Google Fonts. Space Grotesk and Inter appear only as fallbacks in the stack; they are not bundled.
- **Tabular figures.** `.font-mono-code` and `.lys-metric` set `font-variant-numeric: tabular-nums`, so
  counters and meters do not shift width as they update (§2.2).
- **Departure.** The §2.2 unit-separation style (number large, unit small) is not applied yet. Units are shown
  inline next to their values, which keeps the layouts from M3 unchanged.

## 4. Motion (§3, §6.6)

- **Tokens.** Durations `instant` 100ms, `fast` 160ms, `normal` 260ms, `deliberate` 360ms. Easings `hsr`
  cubic-bezier(0.16, 1, 0.3, 1), `zzz` cubic-bezier(0.34, 1.25, 0.64, 1), `standard` cubic-bezier(0.4, 0, 0.2, 1).
- **Transitions only.** Hover and state changes (`transition-colors`, `transition-all`, `transition-opacity`,
  `transition-transform`) take `fast` (160ms, within the 120–180ms micro-feedback band of §3.1) with the
  standard ease. Modal entry takes `deliberate` with the HSR glide (§3.1). List rows enter with a 20ms stagger,
  capped at 180ms in total (§3.2), with a 6px travel (§3.3: no more than 8–16px).
- **Settle states (§3.3.4).** No animation runs continuously. The running dots, the connecting pulse, the
  portrait breathing and scan, the crawl text, and the spinning gyro rings were removed; running is shown by
  its label and colour. The sidebar cube turns only while its brand is hovered. These were the only perpetual
  animations in the console.
- **Departure.** §3.1 names the ZZZ kinetic snap for buttons and tab switches. Its token is declared, but no
  control uses it yet, because the snap is a tactile effect that adds little to an operator console.
- **Departure.** §3.3.2 asks for faster dismissals (120ms). Modals close without an exit animation, so
  dismissals are instant.

## 5. Reduced motion (§7)

- The stylesheet collapses every animation and transition to 0.01ms with a single iteration when
  `prefers-reduced-motion: reduce` is set, as §6 specifies.
- The live-motion default follows the same preference (`prefersReducedMotion()` in `src/theme/motion.ts`).
- Settings shows the motion setting as read-only text. The old "Live motion" switch no longer controlled
  anything, so it was removed rather than left as a fake control.

## 6. Accessibility details (§7)

- **Focus ring.** A 2px gold ring (`--lys-accent-gold`) with a 2px offset on every `:focus-visible` element (§7.2).
- **Escape** closes the job inspector and the dossier image (from M3).
- **Event stream.** The events list is `role="log"` with `aria-live="polite"` and `aria-relevant="additions text"`
  (§7.3), so new events are announced without interrupting.
- **Meters.** Usage meters and job progress use `role="progressbar"` with `aria-valuenow`, `aria-valuemin` and
  `aria-valuemax` (§7.3).
- **Colour is never the only signal.** Every status pip sits next to its text label (§7.1).
- **Departure.** §7.2 suggests `j` and `k` for stepping through the stream and queue. The console uses the arrow
  keys and Home/End, as set in M3.

## 7. What was not done (and why)

- No glow, particle or WebGL backgrounds were added (research §4). The existing decorative cube and rings are
  kept but made still or hover-only.
- No new data was fetched and no behaviour changed. The only logic change is the live-motion default and the
  removal of the non-functional motion switch.
- The per-agent variable values are the research placeholders. The lead replaces them with the palettes
  extracted from the character art; the code does not change.
