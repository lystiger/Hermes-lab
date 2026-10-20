# LysControl M10: compact, summary-first UI with no overlapping text

You are the BUILDER. Repository: the LysControl console (React 19, Vite, TypeScript, Tailwind 4, Vitest). Work in this worktree on the sprint branch.

## Problem (from the operator's screenshots)
- Long values break the layout: prompt file paths such as `/home/lystiger/Projects/Hermes-lab/prompts/lyscontrol-m7-builder.md` spill over neighbouring columns (Queue rows, Job inspector phase list). Job IDs like `run_20261019_115655_lyscontrol-m7-usability` wrap across the table.
- Overlaps: in the Live trace and Events, the source name (`Hermes.scheduler`, `Hermes Runtime`) runs into the event name (`task.created`). In the Job inspector, the runtime event detail text overlaps the event kind.
- Too many words: Overview subtitles, card footers, and explanatory lines repeat what the numbers already say.
- The layout check (`scripts/ui-check.mjs`) reported 0 issues on these screens, because its fixtures are short. It must see long values.

## Goal
1. Overview becomes summary-first: one strip of key numbers (running, queued, blocked, failed, spend, budget), then the active job, the agents, and the live trace. Remove decorative copy. Keep one short line per card at most.
2. Long text never overlaps: give every table or grid cell an explicit min-width and use `min-w-0` on flex children. Long paths and IDs show as a truncated value with the full text in `title`, plus the existing copy control where present. Truncation is allowed only with that tooltip. Source and event columns get fixed widths with a tooltip.
3. Queue rows, Live trace rows, Events rows, and the Job inspector phase list follow the same rule. Phase names show the file name, with the directory in the tooltip.
4. Aesthetics: keep the existing tokens (`var(--lys-*)`), spacing, and card style. Fewer borders and labels, consistent label size, numbers larger than their labels.
5. Test data: add long-text fixtures to the mock adapter (`src/api/adapters/mockAdapter.ts`), for example a 90-character prompt path, a 60-character job ID, and a source named `Hermes.scheduler`. Use them in the tests and in the layout check.

## Constraints
- Do not change the Agents data model (M6) or the request layer.
- Do not weaken existing tests. If an assertion must change because the copy changed, say which one and why in the handoff.
- Reference screenshots are in the operator's Pictures folder and are not in the repo. The repo's current screens are the target.

## Acceptance (all required)
- `npm run typecheck`, `npm run lint`, `npm run test -- --run`, `npm run build` exit 0.
- Add tests: a 90-character path in a Queue row and a 60-character job ID do not produce overlapping elements (use getBoundingClientRect where jsdom allows, or assert the truncation attribute and `title`).
- `SCRATCH=<dir> node scripts/ui-check.mjs <out> http://localhost:3001 6000` shows 0 overlap and 0 clipped-without-tooltip issues at 900, 1280, 1440, and 1920 px, with the long fixtures enabled. Start the dev server yourself with mock mode on (`VITE_LYSCONTROL_MOCK=1 npx vite --port 3001 --strictPort`) and report the exact command.

## Handoff
Write HANDOFF_BUILDER.md: files changed, the before/after word count of the Overview, the ui-check issue counts per width, and anything uncertain. Commit with the message `feat(console): summary-first overview and no overlapping long text`, ending with the trailer `Co-Authored-By: Claude Haiku 5.5 <noreply@anthropic.com>`.
