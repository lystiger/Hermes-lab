# Console: text density and layout

Audit date: 2026-11-06
Auditor role: hardener
Target: `console/src` (routes, components, features, styles)
Scope: too much text, layout density, fixed sizes, wasted width. Visual bugs and dead code are in `visual_bugs_broken_states.md` and `inventory_panels_decisions.md`; only the items that change density are repeated here.

Method and limits:
- Read every route, the shared components, `styles/globals.css`, and the feature components that render visible copy. Line numbers are from the files as they are in this worktree.
- Word counts are whitespace tokens in the literal source text. Interpolated values (`{n}`, `{label}`, URLs) count as one word, so counts marked ≈ are approximate.
- Pixel figures are estimates from Tailwind classes. Nothing was rendered in a browser.
- Tests and the project check were not run, per the task. No git commands were run. No other file was edited.

---

## 1. Summary

1. **One rule, four lines on `/comms`.** "Drafts only, can't start or merge" is stated in two empty states, the composer footer, and the per-reply draft note, which repeats after every reply. About 50 words for one rule.
2. **The unreachable state is shown twice on every page.** The global banner and the page's `ErrorState` both say Hermes is unreachable, and each usually has its own Retry button.
3. **Page headers are tall.** The sticky `PageHeader` takes about 150 px on every page and reserves 58 px for a stat strip even when the strip is empty.
4. **"updated HH:MM:SS" repeats** two or three times per page on Dashboard, Queue and Agent detail, and once per job on Floor.
5. **Boxes inside boxes.** The job inspector and agent dossier nest bordered panels four to five levels deep.
6. **Hover and fallback copy repeats one pattern.** Thirteen visible reason strings (Queue, agent dossier, job inspector) open with "Hermes did not report", "Hermes does not", "Hermes reports no" or "Hermes exposes no".
7. **Fixed sizes fight the content.** A 460 px hero card with a 120 px decorative letter, a `calc(100vh-6rem)` magic offset on Comms, and 256 px Floor columns.
8. **The job inspector is one long page.** Ten or more sections stack in one 90 vh modal, and the trace table silently stops at 50 rows.
9. **A disabled control carries a 13-word tooltip.** "Dispatch" on the agent dossier can never work.

In a spot check of 29 of the quoted strings, the rewrites proposed here total 96 words against 291 now (a 67% cut). Cut rows count as empty.

---

## 2. Too much text

Each row gives the source location, the copy as written, its word count, the verdict, and the proposed replacement. Verdicts: **cut** (remove), **shorten** (keep the fact, fewer words), **merge** (fold into one place).

### 2.1 Repeated across pages

| # | Location | Copy (as written) | Words | Verdict | Proposed |
|---|---|---|---|---|---|
| R1 | `routes/comms.tsx:185` | Ask the orchestrator to draft a brief. It can't start or merge anything. | 13 | ✎ shorten | "Ask for a brief." |
| R2 | `routes/comms.tsx:190` | Type a message to start a chat. Drafts are saved as Draft, never Ready. | 14 | ✎ shorten | "Drafts only, never Ready." |
| R3 | `features/comms/Composer.tsx:96` | The orchestrator drafts briefs only. It cannot start, cancel or merge runs. | 12 | ✎ shorten | "Drafts only. Can't start or merge runs." (keep this one; delete R1 paragraph) |
| R4 | `features/comms/ChatThread.tsx:6`, rendered at `:41` for every reply | Saved to LysStack/drafts as Draft. Only you can mark a brief Ready. | 12 (shown after "Draft saved: …", ≈ 20 total) | ✎ shorten | "Saved as Draft in LysStack." Show once, not per reply. |
| R5 | `routes/comms.tsx:184`, `:189` | What should we plan? (same heading in both empty branches) | 4 | merge | One empty state with one heading. |
| R6 | `components/ConnectionBanner.tsx:25-30` | CAN'T REACH HERMES · API {url} · last successful contact {time} · Retry | ≈ 12 | keep, cut the page copy | Banner stays as the single notice. |
| R7 | `components/DataStates.tsx:38` (title) and `:39` (body) | {label} is not loading. Check that the Hermes runtime API is running at {url}. | ≈ 14 | cut | Body: "Failed to load." Title attribute and the duplicate sentence go. Keep one Retry. |
| R8 | `features/agents/AgentDossier.tsx:23-26` | 4 header tooltips: "Hermes exposes no per-agent run list in this console yet", "Hermes does not report a live activity feed per agent", "Hermes reports no provider quota for this agent", "Hermes does not expose tool or permission grants" | 10, 10, 8, 8 | merge | One "Not reported" legend with four labels, no sentences. |
| R9 | `routes/queue.tsx:12-13` | Hermes exposes no estimator for queued or running work / Hermes does not report a concurrency policy or repository capacity | 9, 10 | ✎ shorten | "No estimator in Hermes" / "No concurrency policy reported" |
| R10 | `features/agents/AgentDossier.tsx:94-98` | five `UnknownValue` reasons: "Hermes did not report a provider", "…a model", "…a focus for this agent", "Hermes reports no current task for this agent", "Hermes reports no active tool for this agent" | 6–8 each | ✎ cut | Show "—" and one shared "Not reported by Hermes" tooltip. Saves about 30 words on one card. |
| R11 | `features/telemetry/ProviderTelemetryList.tsx:28, 50-54` and `features/telemetry/UsageMeters.tsx:82, 91, 99, 107` | Same reasons in both files: "No requests have been made, so no success rate exists" (×2 files), "Provider did not report token usage", "…a remaining request count", "…context use", "…a context window" | 6–10 each | ✎ cut | Shared "Not reported" tooltip. `UsageMeters` is dead code (see visual_bugs note), so this is moot until it is cut. |
| R12 | `features/jobs/JobRealData.tsx:196, 202, 210` | "Hermes did not report a repair count", "…a replan count", "not reported by Hermes for this job" | 7, 7, 7 | ✎ cut | "—" with the shared tooltip. |
| R13 | `features/jobs/JobRunTimeline.tsx:36` and `routes/floor.tsx:78` | No phases reported for this job yet. | 8 | merge | Keep one, in the timeline component. |
| R14 | `routes/settings.tsx:94` | Choose the design direction; the choice is recorded in LysStack for review. | 12 | ✎ shorten | "Recorded in LysStack." |
| R15 | `routes/settings.tsx:98` | Operators come from Hermes (GET /agents). | 6 | cut | The section label already says "Registered operators". |
| R16 | `routes/settings.tsx:47` | reduced (system setting) / full (system setting) | 3 | shorten | "reduced" / "full". The row label already says Motion. |

### 2.2 Help paragraphs and subtitles

| # | Location | Copy | Words | Verdict | Proposed |
|---|---|---|---|---|---|
| H1 | `routes/review.tsx:26` (subtitle) | Finished runs · merge after reading | 6 | ✎ shorten | "Finished runs" |
| H2 | `routes/floor.tsx:35` (subtitle) | Active jobs · by phase | 4 | cut | Subtitle repeats the "Active jobs" stat. |
| H3 | `routes/queue.tsx:35` (subtitle) | Backlog and history | 3 | keep | Only subtitle that adds meaning. |
| H4 | `routes/index.tsx:88` (heading) with `:90` and the subtitle `:65` | "What needs you" (subtitle), "Needs you · N" (heading), "Nothing needs you right now." (empty) | 3 + 3 + 5 | merge | Keep the heading with its count. Drop the subtitle. Empty state becomes "Nothing needs you." (3) |
| H5 | `routes/index.tsx:139` (heading) with `features/agents/RunningPhasesStrip.tsx:22` | "Running now · N" on Dashboard; "Running now · by role" on every agent page | 4, 5 | merge | One "Running" heading per page, with the count. |
| H6 | `routes/execution.tsx:39` | MOCK FIXTURES · not live Hermes data. Start the Hermes runtime API to see real execution state. | 17 | ✎ shorten | "Mock data, not live Hermes." The global mock bar (`components/Layout.tsx:28`, 8 words) already says this. Keep one. |
| H7 | `routes/review.tsx:33` (empty state) | No finished runs yet. A completed goal run appears here with its pull request. | 14 | ✎ shorten | "No finished runs yet." |
| H8 | `routes/review.tsx:95` (title) | Hermes could not open a pull request for this run | 10 | ✎ shorten | "No PR was opened" (the visible label already says "No pull request") |
| H9 | `routes/review.tsx:100` | No verifier verdict was recorded for this run. | 8 | ✎ shorten | "No verdict recorded." |
| H10 | `routes/design.tsx:113` | The Hermes API is not reachable, so a choice cannot be recorded right now. | 14 | ✎ shorten | "Hermes API unreachable: choice not saved." |
| H11 | `routes/design.tsx:123` | Design decided. Waiting for the next design task. | 9 | ✎ shorten | "Decided. Next design task pending." |
| H12 | `routes/design.tsx:168` | This is recorded in LysStack as your decision. Write why, in at least 10 characters. | 15 | ✎ shorten | "Why? (min 10 characters)" as the field label. |
| H13 | `routes/design.tsx:118` | No direction chosen yet. | 5 | cut | The row is empty otherwise; drop the row. |
| H14 | `routes/comms.tsx:166` | Earlier messages summarized | 3 | shorten | "Summarized" |
| H15 | `routes/comms.tsx:197-201` (banner) | Context is 85% full. Compacting keeps replies fast and cheap. (high: "…Compact now so the next reply stays fast and cheap.") | 10 / 14 | ✎ shorten | "Context 85% full." Plus the existing Compact button. |
| H16 | `routes/events.tsx:186` (pill) | 2 new events · back to newest | 7 | ✎ shorten | "2 new ↑" |
| H17 | `features/messaging/OperationalThreadView.tsx:360` (placeholder) | Send operational guidance into job thread... | 6 | ✎ shorten | "Guidance for this job…" |

### 2.3 Tooltips and `title` text

| # | Location | Copy | Words | Verdict | Proposed |
|---|---|---|---|---|---|
| T1 | `features/agents/AgentDossier.tsx:43-60` | "Dispatch" button, disabled, tooltip: "Operator commands are not available: the Hermes API has no command endpoint yet" | 13 | ✎ cut | Remove the control. It is disabled and cannot be used. If it stays, the tooltip becomes "No command endpoint yet" (4). |
| T2 | `features/jobs/JobRealData.tsx:73` | No token usage has been tracked for this job. That is not proof that none was spent. | 17 | ✎ shorten | "No usage tracked; not proof of zero." |
| T3 | `features/floor/FloorCard.tsx:83` | Reported by the agent for every run of this task | 10 | ✎ shorten | "Agent-reported cost" |
| T4 | `features/jobs/JobDetailView.tsx:189-193` | Durable: canonical stored envelope / In-memory event bus: not durable, lost on restart / Live buffer only: received over the stream this session | 4 / 8 / 9 | ✎ shorten | Keep the labels "durable", "in-memory", "live". Put one legend line in the section header. |
| T5 | `components/Sidebar.tsx:123-124` | Connection to the Hermes runtime API · {service} v{version} ({uptime}s uptime) / …not reported by the Hermes API | ≈ 12 | shorten | "Hermes {version} · {uptime}s". |
| T6 | `routes/comms.tsx:162` | Tokens used by the last reply, from the model's own count | 11 | shorten | "Last reply tokens" |
| T7 | `routes/review.tsx:95` (see H8) and `routes/index.tsx:59` | Finished runs whose pull request is open | 7 | cut | The label "TO REVIEW" with its count is enough. |
| T8 | `features/agents/AgentModelSelector.tsx:251` | Applies to the next phase | 5 | keep | Short and says when the change takes effect. |

### 2.4 Verbose and duplicated empty states

| # | Location | Copy | Words | Verdict | Proposed |
|---|---|---|---|---|---|
| E1 | `components/DataStates.tsx:84-89` | `EmptyState` is `p-6`, centred, `gap-3`, 13 px. Used for one-line messages across the app. | — | shorten | Single-line, left-aligned, `py-3`. Long messages go away. |
| E2 | `features/jobs/JobRealData.tsx:177` | EmptyState "No verification recorded" inside a `p-2` box | 3 | ✎ shorten | Plain text line, no padding box. |
| E3 | `routes/comms.tsx:182-191` | Two empty states for the two empty cases (no chat open, and new chat), each with its own heading and paragraph | — | merge | One empty state with one line. |
| E4 | `routes/index.tsx:143` | No run in progress. | 4 | keep | Fine as is. |
| E5 | `routes/queue.tsx:62-68` | Recoverable · 0 (heading) + "No recoverable jobs" (text) in one row | 3 + 3 | ✎ shorten | One row: "Recoverable · 0". |
| E6 | `routes/usage.tsx:110` | No agent limits, in a full `Card` | 3 | cut the card | Plain line. |
| E7 | `routes/events.tsx:128` | No events / No matching events | 2 / 3 | keep | Fine. |

### 2.5 Repeated headings and labels on one page

| # | Where | What repeats | Verdict |
|---|---|---|---|
| D1 | `/agents/:id` | The agent's name appears in the breadcrumb (`components/Header.tsx:34`), the roster card (`features/agents/AgentPresence.tsx:31`), and the dossier heading (`features/agents/AgentDossier.tsx:42`). The initial appears again in the avatar (`AgentPresence.tsx:27`) and as the 120 px hero letter (`AgentDossier.tsx:85`). | Keep the dossier heading. Drop the breadcrumb title. Drop the hero letter. |
| D2 | `components/JobModal.tsx:28` and `features/jobs/JobDetailView.tsx:73` | The job id is shown twice in the same modal (top bar and header). | Keep the header. Drop the top-bar id. |
| D3 | `features/jobs/JobDetailView.tsx:99` and `features/jobs/JobRealData.tsx:80` | Renders as "tokens 1,234 tokens tracked for this job". "tokens" is printed twice. | Show "1,234 tokens", no suffix. |
| D4 | `routes/execution.tsx:39` and `components/Layout.tsx:28` | Two mock banners on one page. | Keep the global bar only. |
| D5 | `routes/execution.tsx:74` (Card label) and `:77` (visible header) | "Recent execution timeline" twice on one card. | Keep the visible header. The `aria-label` stays. |
| D6 | `routes/events.tsx:114` and the table header (`:117-123`) | "N of M shown" plus a six-column header row, plus the pill counts and the stream stat in the page header. | Drop the "N of M shown" text. Keep the counts in the filter pills. |
| D7 | `routes/comms.tsx:167` and `:203` | Two "Compact" buttons on screen at once when the warn banner shows. | Keep the banner button only. |
| D8 | `routes/index.tsx:88` and `:90` | "Needs you" twice in one section (see H4). | Covered by H4. |

### 2.6 Micro-labels

The UI uses 53 `uppercase` labels and 127 instances of `text-[11px]`, plus 41 of `text-[10px]`. Most section titles are 10–11 px uppercase with `tracking-wider`, and the same style is hand-written in several files (`SECTION` constant in `JobRealData.tsx:9`, inline strings elsewhere). There is no single caption style, so it is hard to see which labels matter.

Proposal: one caption token (11 px, uppercase, faint), used by every section title and nothing else. Stat labels in the header stay as they are.

---

## 3. Layout density

### 3.1 Chrome above the content

| Element | Where | Height (estimate) | Note |
|---|---|---|---|
| MOCK bar | `components/Layout.tsx:26-30` | ~26 px | Only in mock mode. |
| Connection banner | `components/ConnectionBanner.tsx:23` | ~40 px | Only when unreachable. Wraps onto two lines at narrow widths. |
| Breadcrumb header | `components/Header.tsx:27` | 44 px fixed | Shows only on `/agents/:id`, and only holds "← Agents" and the agent name. |
| Page header | `components/PageHeader.tsx:24, 39` | ~150 px sticky | `pt-5 pb-4`, title row about 28 px, a `pt-3` separator, and `min-h-[58px]` on the stat strip. The strip is reserved even when there are no stats (for example, while telemetry is loading). |

On Dashboard, Queue, Floor, Usage, Events, Execution, and Settings, the sticky header and any banners take about 150–220 px before the first card. On a 1080 px screen that leaves roughly 860–930 px for content, and the header never scrolls away.

Proposal: one row, title and stat chips inline, about 48 px, no reserved strip.

### 3.2 Padding and spacing stack

- Every route wraps its body in `p-6` with `gap-6` (for example `routes/index.tsx:67`, `routes/queue.tsx:40`, `routes/floor.tsx:39`, `routes/usage.tsx:103`). `p-6` appears 18 times in routes, features and components.
- Cards add their own padding on top: `p-4` (usage cards), `p-5` (review, execution), `p-6` (dossier specs, model selector).
- Inner boxes add more: `p-2` (job diagnostics), `p-3.5` (model configuration blocks), `p-3` (overview attention rows).

Result: a 24 px gap around a card, a 20–24 px card body, and an inner bordered box, with 8–14 px more on each level. Compact tables and lists sit in 40–60 px of padding.

Proposal: page body `p-4 gap-3`. Card body `p-3`. Inner items use dividers, not boxes.

### 3.3 Card nesting

| Where | Nesting (outermost first) | Depth |
|---|---|---|
| Job inspector diagnostics | Modal → column `p-4` → `Section` (`JobRealData.tsx:17`) → `div.p-2` (verification) → `span` | 5 |
| Job inspector REPAIRS / REPLANS | Section → `grid-cols-2` → `div.p-2` → value | 4 |
| Agent dossier specs | `Card` (`AgentDossier.tsx:91`) → `div.p-6` → `grid` → `Spec` | 4 |
| Model configuration | `Card` (`AgentModelSelector.tsx:110`) → `div.p-6` → `div.p-3.5` (configured block) → value | 4 |
| Review run | `article.bg-lys-surface-2.border` → `header` → `dl` → `MetaItem`; and `VerdictBlock` with its own `border-l` and `ul`; and `TaskChain` chips with borders | 4 |

Proposal: two levels maximum on any page: a page section, then rows separated by hairlines.

### 3.4 Fixed heights and widths

| Where | Value | Effect | Proposal |
|---|---|---|---|
| `features/agents/AgentDossier.tsx:83` | `min-h-[460px]` on the hero `Card` | Tall empty decorative card; the 120 px letter (`:84-85`) is the only content. | Drop the hero or cut it to ~200 px. |
| `routes/comms.tsx:139` | `h-[calc(100vh-6rem)] min-h-[520px]` | Magic offset. Comms has no `PageHeader`, so the 96 px gap is unexplained and leaves a blank band under the composer. | `h-full` on the page wrapper, and check it in a browser. |
| `routes/design.tsx:149` | `h-40` on each direction thumbnail | Fixed thumbnails. | Keep; this is a picker. |
| `routes/design.tsx:206` | `h-[520px]` iframe per wireframe | Three 520 px iframes mount when the closed `<details>` is opened. | `h-[360px]` or open one at a time. |
| `routes/floor.tsx:85` | `w-64` per dependency column | 256 px per column. Five columns is about 1,340 px with gaps, so it scrolls sideways on most laptops. | `w-56` or `min-w-48 flex-1`. |
| `features/floor/FloorCard.tsx` | Five stacked rows per card (role, agent, time/cost, latest event or findings, replaced-by) | Each card is tall for a one-line status. | Drop the replaced-by line unless the card is replaced. |
| `features/messaging/OperationalThreadView.tsx:138` | `min-h-[140px] max-h-[380px]` | Thread scrolls inside the inspector, which also scrolls. | One scroll container. |
| `components/NotReported.tsx:33` | `w-72` tooltip | Wide tooltip for short reasons. | `w-56`. |
| `routes/queue.tsx:96` | `max-w-[300px]` | Clips job titles at 300 px while the row has space. | Let the title take the free width. |
| `components/Sidebar.tsx:131` | `w-52` expanded, `w-14` collapsed | 208 px for 11 nav items plus group labels. | Keep; drop the health footer (see 3.6). |
| `routes/index.tsx:67` | `max-w-5xl` | Only page with a max width. At 1920 px the content sits in the left 1,024 px and the rest is empty. Other pages are full width. | Pick one rule for all pages: full width with a two-column grid for Dashboard. |
| `routes/settings.tsx:25`, `:65` | `min-w-[340px]` on each of two columns | Forces a horizontal squeeze at narrow widths. Two columns of 2–4 rows each. | One column; these rows fit a list. |
| `features/agents/AgentDossier.tsx:81` | `grid-cols-[minmax(0,1fr)_minmax(280px,360px)]` at `lg`, `340px` at `xl`, next to `AgentRoster` (`w-80`, 320 px, `features/agents/AgentRoster.tsx:38`) and the 208 px sidebar | At 1440 px: sidebar 208 + roster 320 + hero + details 340, so the hero is squeezed into the middle. | Collapse the roster to a list or move Details below the hero at `lg`. |
| `features/jobs/JobDetailView.tsx:118` | `w-80` artifacts column, shown only when there are artifacts | Layout jumps between jobs with and without artifacts. | Put artifacts in the stacked list, or always reserve the column. |
| `features/jobs/JobDetailView.tsx:73` | `max-w-[40%]` on the job id at `text-[18px]` | Large id beside the title; the id is also in the modal bar (see D2). | Smaller id, or none. |

### 3.5 Job inspector (`components/JobModal.tsx:21`, `features/jobs/JobDetailView.tsx`)

- Ten or more sections stack in one 90 vh modal: header, failure, run timeline, artifacts, thread, diagnostics, tasks, runs, observations, backend execution, runtime events.
- The runtime events table caps at 50 rows (`JobDetailView.tsx:164`, `traceRows.slice(0, 50)`) with no "showing 50 of N" note. The user cannot tell the list is cut.
- The events table uses six columns at `xl` (`:167`), with a `hidden xl:block` split, so the column set changes at one breakpoint.

Proposal: keep the header, failure and timeline open. Put tasks, runs, observations, backend execution and runtime events behind `<details>`, each with its count in the summary. Show "50 of N" when the cap applies.

### 3.6 Repeated status

- The sidebar footer (`components/Sidebar.tsx:197-223`) shows Hermes and Herdr status. The same Hermes status is in the connection banner, and Herdr is on the Execution page. Three places, two states.
- "updated HH:MM:SS" (`components/DataStates.tsx:92-95`) appears on the page header and again on each section:
  - Dashboard: header plus Agents section (`routes/index.tsx:176`), two.
  - Queue: header, Mission board (`features/jobs/MissionBoard.tsx:70`), and Recoverable (`routes/queue.tsx:76`), three when there are recoverable jobs, two when empty.
  - Floor: header plus one per active job (`routes/floor.tsx:134`), N + 1.
  - Agent detail: roster (`AgentRoster.tsx:42`), dossier (`AgentDossier.tsx:55`), and model configuration (`AgentModelSelector.tsx:118`), three.

Proposal: one "updated" per page, in the page header only. Section-level freshness only where a section can fail on its own.

---

## 4. Proposed rules for the redesign

These follow from the findings above. They are inputs to the redesign, not part of this audit.

1. **One caption style.** One uppercase label token. Every section uses it. No other size or case for labels.
2. **One notice per condition.** Unreachable, mock, and stale each appear once, in the banner. Pages do not repeat them.
3. **One help line per page, at most.** Most help text is dropped; a page that needs a line keeps one short line.
4. **Empty states are one line.** Left-aligned, no padding box, no sentence beyond "No X yet."
5. **Unknown values are "—" with a shared "Not reported" tooltip.** No per-field reasons.
6. **Header is one row.** Title and inline stats, no reserved strip.
7. **Two levels of nesting.** Sections, then hairline rows.
8. **Page body `p-4 gap-3`, card body `p-3`.**
9. **Lists cap with a count.** Any capped list says "N of M".
10. **Full width everywhere, one grid rule.** Dashboard uses two columns; other pages are full width.

---

## 5. Cross-references

- Dead components that carry most of the dense copy: `QueueTable`, `ActiveExecutionCard`, `ExecutionResourceCard`, `ExecutionBackendStrip`, `UsageMeters`, `ProviderTelemetryList`, `AgentLaneCard`. None is imported (see `inventory_panels_decisions.md`, dead-code list). Together they are about 850 lines of code (`wc -l`), so removing them takes their copy out of the density picture.
- Invalid colour classes that also break the density look: `text-lys-status-danger` and `text-lys-status-warning` (not defined in `@theme`) at `routes/comms.tsx:161, 180, 197`, `features/comms/ChatSidebar.tsx:55, 59`, and `routes/design.tsx:111, 175`. Unstyled text there reads as body copy. Recorded in `visual_bugs_broken_states.md` and `inventory_panels_decisions.md`.
- The "3D Ambient Rings" toggle (`routes/settings.tsx:50-58`) changes state that nothing reads, so it adds a row and does nothing. Recorded in `inventory_panels_decisions.md`.
- Crash risk in the same files, not a density issue: `features/agents/AgentPresence.tsx:27` and `AgentDossier.tsx:85` read `displayName[0]` without a null check.

---

## 6. Not checked

- Nothing was rendered. Pixel heights are from class values. A browser pass is needed before the header and hero numbers are quoted as measurements.
- The copy in `features/messaging/OperationalThreadView.tsx` (462 lines) was scanned for prose, not read line by line. Its visible copy is mostly labels and one placeholder (`:360`).
- `features/jobs/JobRealData.tsx` was read in part (sections, tokens, diagnostics). The observations and runs panels were read only for their empty states.
- Tests and the project check were not run, per the task instruction.
