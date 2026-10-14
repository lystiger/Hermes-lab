# LysControl usable-console spec (FE lead)

Goal: LysControl shows only real Hermes data, is readable at a glance, and easy to operate.
Sources: `docs/api-audit.md` (what is real, false or missing) and `docs/design/mihoyo-ui-research.md` (visual and motion language).

## Non-negotiable rules
1. **Truth over looks.** Nothing on screen may claim a fact that no Hermes endpoint backs. Unknown is shown as unknown ("—" + reason on hover), never as 0, never as a plausible number. The research mockups invent fields (temperature, max tokens, capability radar, "Emergency Intervene", seat numbers); do NOT build those. Style only real data.
2. **Real by default.** HTTP mode against `http://localhost:8000` is the default. Mock data only with an explicit `VITE_LYSCONTROL_MOCK=1`, and then a persistent "MOCK DATA" banner. `VITE_LYSSTACK_API_URL` still overrides the URL.
3. **Every data view has 4 states:** loading, error (with the actual error and a retry), empty (honest sentence), data (with a freshness time). One shared component set for these.
4. **No fake actions.** Buttons that cannot do anything real are removed or disabled with a tooltip saying why. A failed action keeps the user's input.
5. **Accessibility:** WCAG 2.1 AA contrast, visible keyboard focus, `prefers-reduced-motion` respected, no continuous animation while idle.
6. Each milestone: `npm run typecheck && npm run lint && npm run test -- --run && npm run build` green, tests for new behaviour, one commit, then STOP and print a summary. The lead reviews before the next milestone.

## Milestones
- **M1 — Truth.** Real-by-default client (rule 2). All audit P1 items: remove every fabricated metric, ETA, budget, quota, projection, badge count, trace id, clock and success claim; derive what can be derived (counts, elapsed from timestamps); otherwise honest unknown. Disable or relabel the generic dispatcher. Herdr shown as "on PATH", not "online". Fetch errors are shown, not hidden as "no data". Shared loading/error/empty/freshness components (rule 3). Tests: no HTTP-mode widget renders an unbacked number.
- **M2 — Real data (frontend only).** Audit P2 items that need no backend change: capacity/job telemetry DTOs + adapters and their widgets (with unknown/estimated states); keep runId/actorId; job detail shows tasks, runs, observations, job events, failure explanation; refresh identity/telemetry after reconnect and on relevant events. Contract tests with observed JSON (incl. nulls).
- **M3 — Readable and easy.** Information architecture per research §5, using only real fields: Agents roster + dossier, Queue as a mission board grouped by status, Execution as the deployed party, Events as a filterable log (failure taxonomy), Usage as meters with window labels. Consistent page headers, filters, keyboard navigation (Esc closes, arrows in lists), copyable IDs, timezone-consistent times.
- **M4 — Theme and motion.** Research §6 tokens as CSS custom properties + Tailwind theme; fonts via @fontsource (OFL: Outfit, Plus Jakarta Sans, JetBrains Mono); per-agent accents; motion tokens (durations, easings) on transitions only; reduced-motion fallback; contrast check of every token pair used for text.
- **M5 — Lead + Codex verification.** Codex re-runs the API audit against the result; the lead reviews UX end to end.

Out of scope here (lead handles in Hermes): the `/jobs/recoverable` route shadowing, mutation endpoints (create/cancel/resume), personas.
