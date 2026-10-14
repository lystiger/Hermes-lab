# M3 decisions: readable and easy (research §1 and §5)

Layout source: `docs/design/mihoyo-ui-research.md` §1 (navigation paradigms) and §5 (domain mapping).
Rule applied throughout: **real data only**. Where the research shows a field Hermes does not provide,
the field is left out or shown as unknown with the reason on hover. Nothing is invented to match a mockup.
Colours, fonts and the theme are unchanged (M4).

## Global

- **Connection banner (lead requirement).** Whenever a request to Hermes fails at the network level, a
  banner names the API URL, the last successful contact (or "none this session") and offers a retry. Data
  panels say "Can't reach Hermes" instead of looking empty. Source: `src/components/ConnectionBanner.tsx`,
  `src/api/connection.ts`. Research: none (this is an operator requirement).
- **Keyboard (rule 5).** Escape closes the job inspector and the dossier image. Up/Down, Home and End move
  through lists marked `data-nav-item` (agent roster, job board, event log). Visible focus ring in
  `globals.css`. Research §1.1 suggests `1`–`3` quick-switch keys; we use arrows instead, because the
  roster is not a fixed set of three.
- **Copyable IDs.** Job, agent, run, task and event IDs use `CopyId`. Research: none (operator need).
- **Time.** One local format (`src/features/time/format.ts`). Event times come from the epoch seconds, not
  the server's display string. Missing times are shown as unknown.
- **Filters.** `FilterPills` with live counts, the pattern from research §1.4 (`All (48)` style).

## Agents (`/agents`, `/agents/:id`): §5.1 roster and dossier

- **Applied:** §1.1 split pane. Roster on the left with status pip and status filter (counts from
  Hermes status values). Dossier on the right with name, status, model, provider, role, phase, current
  task, active tool, capabilities, context window, allowance and run/activity sections.
- **Departures (not provided by Hermes):**
  - Temperature, max tokens, backend seat, active job per agent: not in `GET /agents`. Omitted.
  - Capability radar and tool/permission matrix: no permission data exists. Omitted.
  - "Emergency intervene", "evacuate context", "new agent": no endpoint. Omitted.
  - Token share percentages on roster cards (`Tokens: 412k (82%)`): no per-agent tokens. Omitted.
  - Context window: shown as unknown with the reason. The meter draws no bar.
  - "Dispatch task": disabled with the reason (no command endpoint).
- **Kept:** the existing honest unknowns for activity, runs and allowance.

## Queue (`/queue`): §5.2 mission board

- **Applied:** commission cards grouped by status (Running, Blocked, Queued, Failed, Completed,
  Cancelled, plus any unrecognised status as its own column). Each card has ID, title, repository,
  branch, assigned agents, phase, progress (only when reported), start time and blocked reason. Failed
  jobs show a "Mission interrupted" note in place of a silent red highlight (research §5.2).
- **Departures:**
  - Concurrency lanes per repository (`2/2 seats`): Hermes reports no repository capacity. Omitted.
  - Priority: shown only when Hermes reports it. The adapter's invented `P1` default is removed.
  - Progress as phase `3/5` and queue position / ETA: no phase total and no estimator. Omitted.
  - Inline "inspect logs", "force retry", "reassign seat", "create job": no endpoints (M2 scope: read-only).
  - "Analyze failure with agent" CTA: no action exists. The note points to the job inspector instead.
  - Drag-to-reorder priority: no reorder endpoint. Omitted.
- **Kept:** recoverable jobs list (read-only, from M2) and the execution-order phases of the active job.

## Execution (`/execution`): §5.3 deployed seats

- **Applied:** seat cards numbered `SEAT 01…` within each backend group. Each shows state, job and task
  IDs (copyable), execution ID, reuse and generation badges, idle expiry countdown (real `expiresAt`), and
  failure detail. Backend strip with availability and the OpenRig ledger.
- **Departures:**
  - Memory and CPU gauges and "pooled TTL" ring: the snapshot carries no usage numbers. Omitted.
  - Occupant agent avatar on each seat: the snapshot names no occupant agent. Omitted.
  - Stdout, recycle, kill and attach-terminal buttons: no endpoints. Omitted.
  - "Heartbeat 24ms": not measured. Replaced by the snapshot's loaded time.

## Events (`/events`): §5.4 filterable log

- **Applied:** filter strip with counts for each category and source, a ledger with time, severity pip,
  source, kind, detail and job. Clicking a row expands it to the event JSON with copyable IDs. The
  Errors filter uses the real failure taxonomy (`*.failed`, `*.release_failed`, `error`); retries and
  quota warnings are a separate "Warnings" category.
- **Departures:**
  - "120 evt/min" stream rate: not computed; no rate is claimed.
  - Side drawer for the payload: an inline expansion is used instead, so the list keeps its place.
  - Payload-summary highlighting: the detail text is shown as Hermes sends it.
  - Severity labels "OK / WARN / ERR": derived from the taxonomy only; "info" for everything else.

## Usage (`/usage`): §5.5 meters with window labels

- **Applied:** meter cards from capacity telemetry. Each meter carries its window. Totals are labelled
  "since runtime start (process lifetime, not daily)". A bar is drawn only when both the value and its
  limit are reported.
- **Departures (the research shows daily and weekly figures; Hermes provides neither):**
  - "Daily token allowance", "weekly enterprise budget", "full recovery in 09h", burn rate per hour: no
    daily or weekly data and no budget exists. Omitted. Every total is process-lifetime.
  - Provider reset countdown: shown only when the provider reports `resetAt`, as text.
  - Model fallback routing table: no routing data. Omitted.
  - Circular gauges: rendered as bars, since the bar is the only meter the data supports.
- **Kept:** run budget and queue projection stay as honest unknowns (no source in Hermes).
