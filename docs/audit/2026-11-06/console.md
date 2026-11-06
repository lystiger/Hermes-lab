# Operator Console Audit and Compact Redesign

Audit date: 2026-11-06  
Scope: `console/src` (routes, pages, panels, components, styles)

---

## 1. Findings Table

| id | severity | finding | file:line | proposed fix |
|---|---|---|---|---|
| F-01 | high | Review card shows "Open pull request" regardless of `prState`; merged/closed PR appears open | `console/src/routes/review.tsx:66,83-96` | Render `prState` badge and disable action button if MERGED or CLOSED |
| F-02 | high | Floor job header status hardcoded to `text-lys-success`; FAILED and BLOCKED jobs show green | `console/src/routes/floor.tsx:125` | Map job status to theme colors (`lys-danger`, `lys-warning`, `lys-info`, `lys-success`) |
| F-03 | high | Dashboard attention and review counts default to empty array on load/error, falsely claiming "Nothing needs you" | `console/src/routes/index.tsx:32,38-40` | Render loading spinner and error alert instead of defaulting reviews to empty list |
| F-04 | high | Dashboard, Floor, and Queue silently retain stale metrics on failed refresh without stale warning | `console/src/routes/index.tsx:33,68`, `console/src/routes/floor.tsx:21,41,77`, `console/src/api/hooks.ts:103-106` | Render visible stale warning badge whenever hook `stale` flag is true |
| F-05 | high | Recoverable jobs copy button nested in `role="button"` div with `preventDefault`; keyboard Enter opens job instead of copying | `console/src/routes/queue.tsx:82-95` | Separate copy control from row click target and use semantic button elements |
| F-06 | high | Settings operator rows are non-keyboardable divs and page sets `select-none`, blocking copy and keyboard navigation | `console/src/routes/settings.tsx:20,71-74` | Cut Settings page; merge operator list into semantic `/agents` table |
| F-07 | high | Comms sidebar hidden below `md` breakpoint (`hidden md:flex`) with no mobile fallback, locking out chat selection/creation | `console/src/routes/comms.tsx:140` | Add collapsible drawer or dropdown selector for conversations on narrow viewports |
| F-08 | high | Comms race condition: async conversation fetch overwrites current selection if earlier request resolves late | `console/src/routes/comms.tsx:42-45,64-66,70-72` | Discard out-of-order responses using request ID tracking or AbortController |
| F-09 | high | Comms clears draft before API call succeeds, losing unsent operator prompt on network failure | `console/src/routes/comms.tsx:53-61,68-74` | Clear draft input only after send promise successfully resolves |
| F-10 | high | Undefined CSS classes (`text-lys-status-danger`, `text-lys-status-warning`, `border-lys-status-danger`, `bg-lys-surface-3`) silently drop alert styles | `console/src/styles/globals.css:9-34`, `console/src/routes/comms.tsx:161,180,197` | Declare missing color and surface design tokens in `globals.css` `@theme` block |
| F-11 | high | Avatar initial crashes with TypeError if `displayName` is empty or undefined | `console/src/features/agents/AgentPresence.tsx:27`, `console/src/features/agents/AgentDossier.tsx:85` | Add safe navigation and fallback: `displayName?.[0] ?? '?'` |
| F-12 | medium | Job trace table lacks loading indicator; displays blank box when durable history is loading | `console/src/features/jobs/JobDetailView.tsx:157-164` | Display `LoadingState` while `durable.loading` is true and live buffer is empty |
| F-13 | medium | Job trace list silently capped at 50 rows without indicator or link to full log | `console/src/features/jobs/JobDetailView.tsx:164` | Add "Showing 50 of N events" note and deep link to `/events?jobId={id}` |
| F-14 | medium | Queue duplicate loading indicator shown in both route and `MissionBoard` component | `console/src/routes/queue.tsx:42`, `console/src/features/jobs/MissionBoard.tsx:74` | Remove route-level `LoadingState`, keeping `MissionBoard` internal state |
| F-15 | medium | Recoverable jobs list displays retained stale rows under full error banner | `console/src/routes/queue.tsx:79-81` | Render subtle inline stale chip over cached items instead of blocking error banner |
| F-16 | medium | Usage route header hides capacity errors and stale totals | `console/src/routes/usage.tsx:77-80,90-94,103-106` | Surface `capacityError` and `capacityStale` in header stat chips |
| F-17 | medium | Comms initial and chat loads lack loading indicators, prematurely displaying new-chat empty prompt | `console/src/routes/comms.tsx:34-45,187-190` | Add loading spinner while conversation list and messages load |
| F-18 | medium | Cell `ErrorState` has `m-4 p-4`, causing table row layout blowout on model save failure | `console/src/routes/agents/index.tsx:101`, `console/src/components/DataStates.tsx:34` | Replace cell-level `ErrorState` with compact 11px inline text alert |
| F-19 | medium | Unscoped `useConsoleStore()` calls in 11 components trigger re-render every second on `tickClock` | `console/src/stores/useConsoleStore.ts:218-234` | Use targeted zustand selectors for specific state slices |
| F-20 | medium | Sidebar keyboard listener re-binds on every render due to missing `useEffect` dependency array | `console/src/components/Sidebar.tsx:90-99` | Pass empty dependency array `[]` to listener registration hook |
| F-21 | medium | Case mismatch risk in agent model lookup (`models[agentId.toLowerCase()]` vs `models?.[agent.id]`) | `console/src/features/agents/AgentModelSelector.tsx:29`, `console/src/routes/agents/index.tsx:140` | Normalize all agent IDs to lowercase across stores and views |
| F-22 | low | Duplicate mock banner in `ExecutionRoute` and shell `Layout.tsx` | `console/src/routes/execution.tsx:37-41`, `console/src/components/Layout.tsx:26-30` | Remove route-level mock banner in `execution.tsx` |
| F-23 | low | Settings "3D Ambient Rings" toggle writes to unused store flag; `AmbientGyro` never mounted | `console/src/routes/settings.tsx:50-58` | Remove toggle and delete unused store property |
| F-24 | low | Disabled "Dispatch" button displays 13-word tooltip explaining missing backend endpoint | `console/src/features/agents/AgentDossier.tsx:56-64` | Remove dead button |
| F-25 | low | Redundant "updated HH:MM:SS" freshness timestamps repeated 2-4 times per page | `console/src/components/DataStates.tsx:92-96`, `console/src/routes/floor.tsx:134` | Render freshness timestamp solely in page header |
| F-26 | low | Token count prints duplicate word ("tokens 1,234 tokens tracked") | `console/src/features/jobs/JobDetailView.tsx:99`, `console/src/features/jobs/JobRealData.tsx:80` | Format string as "1,234 tokens tracked" |
| F-27 | low | Catch-all route silently redirects mistyped or obsolete URLs to `/` without feedback | `console/src/App.tsx:33` | Redirect with toast notification or render compact 404 page |
| F-28 | low | Overuse of micro-labels (180+ instances of `<=11px` text) with inconsistent casing | `console/src/features/jobs/JobRealData.tsx:9` | Standardize on single 11px uppercase muted caption token |
| F-29 | low | Sticky `PageHeader` occupies ~150px and reserves 58px empty stat strip | `console/src/components/PageHeader.tsx:15-63` | Compress header into single inline 44px bar |
| F-30 | low | Dead unmounted components totaling 850+ lines of code | `console/src/components/AmbientGyro.tsx`, `console/src/features/tools/ToolCallItem.tsx`, etc. | Delete unreferenced component files |

---

## 2. High-Severity Findings

### F-01: Pull request state ignored on review cards (`routes/review.tsx:66,83-96`)
Review cards render an "Open pull request" link for any item with a `prUrl`, ignoring `prState` (`OPEN`, `MERGED`, `CLOSED`). A merged PR looks identical to an unmerged PR awaiting human approval. Operators cannot determine review status without navigating away to GitHub.

### F-02: Hardcoded green success color on Floor job header (`routes/floor.tsx:125`)
The job header status label unconditionally applies `text-lys-success`. Active runs in `FAILED` or `BLOCKED` states display green success badges while their underlying phase cards show red failure indicators. Operators glance at green headers and miss stalled or failed pipelines.

### F-03: Dashboard falsely claims nothing needs attention (`routes/index.tsx:32,38-40`)
`OverviewRoute` extracts `reviews` from `useReviews()`, which defaults to an empty array during initial loading or network errors. Because review items disappear, the triage section evaluates to empty and renders "Nothing needs you right now." Operators are misled into believing systems are healthy when API fetches fail.

### F-04: Silent stale data retention across monitoring views (`routes/index.tsx:33`, `routes/floor.tsx:21`, `api/hooks.ts:103-106`)
Data hooks cache previous payloads on background refresh failures. Neither Dashboard nor Floor checks the exposed `stale` boolean. Stalled runs, stale queue lengths, and unrefreshed token pools remain static without visual error or warning badges.

### F-05: Keyboard inaccessible copy button in recoverable queue (`routes/queue.tsx:82-95`)
The `CopyId` button is nested inside an outer `role="button"` div with an Enter key handler executing `e.preventDefault()`. Keyboard users tabbing to the copy button and pressing Enter trigger row selection instead of clipboard copying, making ID copying mouse-only.

### F-06: Mouse-only operator rows and global text unselectable (`routes/settings.tsx:20,71-74`)
The Settings page wraps root content in `select-none`, preventing operators from copying environment configs or model names. Operator rows are clickable `div`s lacking `tabIndex`, keyboard event handlers, and ARIA roles.

### F-07: Comms conversation sidebar hidden on mobile/narrow viewports (`routes/comms.tsx:140`)
The conversation sidebar uses class `hidden md:flex` with no responsive drawer or mobile menu button. Below 768px, operators cannot switch chats, view history, or create new planning drafts.

### F-08: Unbounded race condition in Comms chat switching (`routes/comms.tsx:42-45,64-72`)
Selecting conversation A then B triggers asynchronous requests without cancellation. If A's response resolves after B's, the UI displays A while indicating B is selected. Operator messages are sent to the wrong thread.

### F-09: Unsent draft discarded on Comms send failure (`routes/comms.tsx:53-61,68-74`)
The composer resets local input state via `setDraft('')` prior to awaiting API conversation creation. When network requests fail, the catch block logs the error but does not restore input text, destroying typed operator prompts.

### F-10: Undefined color tokens silently drop warning/danger styles (`globals.css:9-34`, `routes/comms.tsx:161`)
Classes `text-lys-status-danger`, `text-lys-status-warning`, `border-lys-status-danger`, and `bg-lys-surface-3` are omitted from the Tailwind `@theme` configuration. Elements fall back to unstyled inherited colors, concealing critical error boundaries and warnings.

### F-11: Avatar initial crash on missing display name (`AgentPresence.tsx:27`, `AgentDossier.tsx:85`)
Components index `displayName[0]` directly without optional chaining or empty string checks. If Hermes returns an agent object with an empty or missing `displayName`, the console crashes with an unhandled TypeError.

---

## 3. Inventory and Keep / Merge / Cut Verdicts

Criteria: Keep only routes and panels that directly enable operators to run jobs (start, monitor, unblock, configure execution) or verify jobs (inspect outputs, failures, evidence, PRs). Cut or merge everything else.

### 3.1 Routes

| Route | File:Line | Operator Decision Supported | Helps Run/Verify | Verdict |
|---|---|---|---|---|
| `/` | `console/src/routes/index.tsx:30` | What failed, blocked, or requires immediate triage? | Y (Triage) | **KEEP** |
| `/queue` | `console/src/routes/queue.tsx:16` | Which jobs are queued, running, failed, or recoverable? | Y (Run) | **KEEP** |
| `/floor` | `console/src/routes/floor.tsx:20` | Where is each active phase, and is a repair stuck? | Y (Run/Verify) | **KEEP** (Cards view only) |
| `/review` | `console/src/routes/review.tsx:15` | Is completed work verified and ready to merge? | Y (Verify) | **KEEP** |
| `/agents` | `console/src/routes/agents/index.tsx:108` | Which model, effort, and quota will next phase use? | Y (Run) | **KEEP** (Absorbs `/usage` & operator list) |
| `/agents/:agentId` | `console/src/routes/agents/$agentId.tsx:6` | Inspect character card and lore dossier | N | **CUT** |
| `/usage` | `console/src/routes/usage.tsx:76` | Can agents accept work without throttling? | Y (Run) | **MERGE → `/agents`** |
| `/events` | `console/src/routes/events.tsx:19` | What runtime events, tool calls, and failures occurred? | Y (Verify) | **KEEP** |
| `/execution` | `console/src/routes/execution.tsx:11` | Are sandboxes and execution backends ready? | Y (Run) | **KEEP** (Trimmed) |
| `/comms` | `console/src/routes/comms.tsx:14` | Draft project brief to initiate future runs | Borderline | **KEEP** (Flagged borderline; brief drafts only) |
| `/settings` | `console/src/routes/settings.tsx:8` | View static runtime facts and toggle 3D rings | N | **CUT** (Facts → Sidebar footer, operators → `/agents`) |
| `/design` | `console/src/routes/design.tsx:38` | Choose visual aesthetic moodboard for Unigreen | N | **CUT** (LysStack graphic design concern) |
| `*` | `console/src/App.tsx:33` | Fallback recovery route | Indirect | **KEEP** (Plumbing) |

### 3.2 Shell and Top-Level Overlays

| Component / Panel | File:Line | Operator Decision Supported | Helps Run/Verify | Verdict |
|---|---|---|---|---|
| Mock Data Banner | `console/src/components/Layout.tsx:26-30` | Am I viewing real Hermes data or test fixtures? | Y (Trust) | **KEEP** (Single global instance) |
| Connection Banner | `console/src/components/ConnectionBanner.tsx:11-40` | Is Hermes runtime reachable? | Y (Safety) | **KEEP** (Shorten text) |
| Agent Header Back-Bar | `console/src/components/Header.tsx:5-41` | Navigate back from agent dossier | N | **CUT** (Dead with `/agents/:id` cut) |
| Page Header & Stat Strip | `console/src/components/PageHeader.tsx:15-63` | Identify view and top-level metrics | Y | **KEEP** (Compress to 44px single row) |
| Freshness Timestamp | `console/src/components/DataStates.tsx:92-96` | Is displayed data current? | Y | **KEEP** (Header only) |
| Unreported Metrics Tooltip | `console/src/components/NotReported.tsx:14-51` | Read why Hermes omitted telemetry numbers | N | **CUT** (Replace with simple "—") |
| Navigation Sidebar | `console/src/components/Sidebar.tsx:28-54` | Navigate between console modules | Y | **KEEP** (Reduce to 8 items) |
| Sidebar Badges | `console/src/components/Sidebar.tsx:105-111` | Check pending queue depth and active runs | Y | **KEEP** (Queue & Execution counts; cut live/agent badges) |
| Sidebar Runtime Footer | `console/src/components/Sidebar.tsx:197-223` | Verify Hermes and Herdr daemon status | Y | **KEEP** (Absorbs Settings runtime facts) |
| Job Inspector Modal | `console/src/components/JobModal.tsx:8-41` | Detailed root-cause debugging and verification | Y (Verify) | **KEEP** (Core inspector) |
| Dossier Modal | `console/src/components/DossierModal.tsx:6-59` | View character portrait artwork | N | **CUT** |

### 3.3 Dashboard Panels (`/`)

| Panel | File:Line | Operator Decision Supported | Helps Run/Verify | Verdict |
|---|---|---|---|---|
| Stat Strip (6 metrics) | `console/src/routes/index.tsx:42-61` | System triage overview | Y | **MERGE** (Keep 5 operational metrics; CUT TOKENS spend) |
| Telemetry Error / Stale | `console/src/routes/index.tsx:68-69` | Is dashboard data valid? | Y | **KEEP** |
| "Needs You" Attention List | `console/src/routes/index.tsx:86-134` | What failed, paused, or blocked runs require action? | Y | **KEEP** (Core panel) |
| "Running Now" List | `console/src/routes/index.tsx:136-166` | What runs are actively executing? | Y | **KEEP** |
| Agents Summary List | `console/src/routes/index.tsx:168-188` | Which agents exist? | N | **CUT** (Redundant with `/agents`) |

### 3.4 Queue Panels (`/queue`)

| Panel | File:Line | Operator Decision Supported | Helps Run/Verify | Verdict |
|---|---|---|---|---|
| Queue Stat Strip | `console/src/routes/queue.tsx:21-28` | Backlog count and distribution | Y | **MERGE** (Inline into MissionBoard header) |
| Mission Board Columns | `console/src/features/jobs/MissionBoard.tsx:39-118` | Inspect work in pending, running, or failed state | Y | **KEEP** |
| Mission Board Status Chips | `console/src/features/jobs/MissionBoard.tsx:99-113` | Filter board by status | Y | **KEEP** (Dense single row) |
| Job Cards | `console/src/features/jobs/MissionBoard.tsx:120-182` | Identify job, repo, branch, priority, progress | Y | **KEEP** (Cut card copy ID, cut start time) |
| "Mission Interrupted" Note | `console/src/features/jobs/MissionBoard.tsx:173-177` | Identify failed run | N | **CUT** (Status column already states failed) |
| Recoverable Jobs Card | `console/src/routes/queue.tsx:59-104` | Identify stopped runs capable of resumption | Y | **MERGE** (Fold as filter chip on Mission Board) |

### 3.5 Review Panels (`/review`)

| Panel | File:Line | Operator Decision Supported | Helps Run/Verify | Verdict |
|---|---|---|---|---|
| Review Stat Strip | `console/src/routes/review.tsx:19-22` | Number of completed runs needing PR review | Y | **KEEP** |
| Review Run Cards | `console/src/routes/review.tsx:55-64` | Identify goal, branch, repair iterations, cost | Y | **KEEP** |
| PR Link & Status Badge | `console/src/routes/review.tsx:83-96` | Open PR; verify merge readiness | Y | **KEEP** (Fix F-01 to show `prState`) |
| Verification Verdict Block | `console/src/routes/review.tsx:98-118` | Read verifier findings and pass/fail verdict | Y (Verify) | **KEEP** (Core verification panel) |
| Task Chain | `console/src/routes/review.tsx:121-142` | Inspect execution sequence and replaced checks | Y (Verify) | **KEEP** |

### 3.6 Floor Panels (`/floor`)

| Panel | File:Line | Operator Decision Supported | Helps Run/Verify | Verdict |
|---|---|---|---|---|
| Active Jobs Stat Strip | `console/src/routes/floor.tsx:28` | Total running pipelines | Y | **MERGE** (Move into header subtitle) |
| Job Header | `console/src/routes/floor.tsx:121-132` | Job title, repair cycle counter | Y | **KEEP** (Fix F-02 green status bug; cut spend) |
| Cards / Timeline Toggle | `console/src/routes/floor.tsx:135-149` | Switch between phase cards and timeline | N | **CUT** (Keep cards view; timeline exists in inspector) |
| Phase Card: Role / Agent | `console/src/features/floor/FloorCard.tsx:42-99` | Who is running phase and in what state? | Y | **KEEP** |
| Phase Card: Elapsed Time | `console/src/features/floor/FloorCard.tsx:81-82` | Detect hung or stalled phase | Y | **KEEP** |
| Phase Card: Latest Event | `console/src/features/floor/FloorCard.tsx:89-91` | What is active phase doing right now? | Y | **KEEP** (Single line) |
| Phase Card: Findings List | `console/src/features/floor/FloorCard.tsx:101-114` | Inspect failing test or check finding | Y (Verify) | **KEEP** |
| Phase Card: Cost | `console/src/features/floor/FloorCard.tsx:47,83` | Track phase token cost | N | **CUT** (Spend metric) |

### 3.7 Events Panels (`/events`)

| Panel | File:Line | Operator Decision Supported | Helps Run/Verify | Verdict |
|---|---|---|---|---|
| Stat Strip (4 metrics) | `console/src/routes/events.tsx:89-94` | Stream status and error totals | Y | **MERGE** (Keep FAILURES, WARNINGS, STREAM; cut EVENTS HELD) |
| Filter Pills | `console/src/routes/events.tsx:73-85` | Filter log by severity and event source | Y | **KEEP** (Cap source list width) |
| Event Stream Table | `console/src/routes/events.tsx:117-157` | Forensic log debugging | Y (Verify) | **KEEP** |
| Raw JSON Dump Row | `console/src/routes/events.tsx:159-171` | Inspect full error envelope and payload | Y (Verify) | **KEEP** (Collapsed by default) |
| Scroll Freeze Pill | `console/src/routes/events.tsx:179-189` | Prevent jump to bottom during live streaming | Y | **KEEP** (Shorten text to "N new ↑") |

### 3.8 Execution Panels (`/execution`)

| Panel | File:Line | Operator Decision Supported | Helps Run/Verify | Verdict |
|---|---|---|---|---|
| Stat Strip | `console/src/routes/execution.tsx:19-21` | Available sandbox runners | Y | **KEEP** |
| Backend Status Cards | `console/src/routes/execution.tsx:56-71` | Verify herdr CLI and execution engines | Y | **KEEP** (Single-line detail) |
| Recent Execution Timeline | `console/src/routes/execution.tsx:74-82` | Backend event history | N | **CUT** (Redundant with `/events` filtered by execution) |
| Unmounted Backend Strips | `console/src/features/execution/*` | Resource allocation | N | **CUT** (Dead code) |

### 3.9 Comms Panels (`/comms`)

| Panel | File:Line | Operator Decision Supported | Helps Run/Verify | Verdict |
|---|---|---|---|---|
| Chat Thread List | `console/src/features/comms/ChatSidebar.tsx:17-84` | Select, rename, delete draft briefs | Borderline | **KEEP** (Add mobile drawer) |
| Model & Effort Select | `console/src/routes/comms.tsx:156-176` | Choose model to draft brief | Borderline | **MERGE** (Combine into single compact row) |
| Context Meter & Banner | `console/src/routes/comms.tsx:160-206` | Track context usage and trigger compaction | Borderline | **CUT** (Keep one compact button in header; cut duplicate banner) |
| Chat Thread & Reply | `console/src/features/comms/ChatThread.tsx:17-62` | Read orchestrator draft | Borderline | **KEEP** |
| Per-Reply Draft Saved Note | `console/src/features/comms/ChatThread.tsx:48-53` | Confirm file save location | Borderline | **MERGE** (Single line footer, not repeated per message) |
| Message Composer | `console/src/features/comms/Composer.tsx:13-37` | Send brief prompt to orchestrator | Borderline | **KEEP** (Shorten footnote disclaimer) |

### 3.10 Usage Panels (`/usage` → Merged into `/agents`)

| Panel | File:Line | Operator Decision Supported | Helps Run/Verify | Verdict |
|---|---|---|---|---|
| Stat Strip | `console/src/routes/usage.tsx:88-95` | Throttling and capacity | Y (Partial) | **MERGE → `/agents`** (Keep THROTTLING; cut TOKENS, REQUESTS, SUCCESS RATE) |
| Agent Limit Cards | `console/src/routes/usage.tsx:25-73` | Remaining % and reset timestamps | Y | **MERGE → `/agents`** (Add as columns in agent table) |
| Auth Help Callout | `console/src/routes/usage.tsx:69` | Unblock agent authentication failures | Y | **MERGE → `/agents`** (Show only on auth error) |

### 3.11 Agents Panels (`/agents` & `/agents/:agentId`)

| Panel | File:Line | Operator Decision Supported | Helps Run/Verify | Verdict |
|---|---|---|---|---|
| Agents Table | `console/src/routes/agents/index.tsx:24-105` | Configure model and reasoning effort per agent | Y (Run) | **KEEP** (Primary configuration view; absorbs usage limits) |
| Agent Roster & Presence | `console/src/features/agents/AgentPresence.tsx:11-56` | View agent identity and status | N | **CUT** (Table provides status) |
| Running Phases Strip | `console/src/features/agents/RunningPhasesStrip.tsx:15-61` | View active role assignments | N | **CUT** (Redundant with Floor) |
| Agent Dossier & Specs | `console/src/features/agents/AgentDossier.tsx:40-99` | Persona bio and decorative specs | N | **CUT** (Move active tool to table column) |
| Hero Portrait & Modal | `console/src/features/agents/AgentDossier.tsx:83-87` | 120px decorative letter card | N | **CUT** |
| Duplicate Model Selector | `console/src/features/agents/AgentModelSelector.tsx:26-271` | Duplicate model editor | N | **CUT** (Consolidate into `/agents` table) |

### 3.12 Settings Panels (`/settings` → Cut Page)

| Panel | File:Line | Operator Decision Supported | Helps Run/Verify | Verdict |
|---|---|---|---|---|
| Runtime & Environment Facts | `console/src/routes/settings.tsx:23-36` | View version and uptime | Rare | **MERGE** (Fold into Sidebar footer tooltip) |
| 3D Ambient Rings Toggle | `console/src/routes/settings.tsx:50-58` | No-op visual toggle | N | **CUT** |
| Registered Operators List | `console/src/routes/settings.tsx:64-83` | Inspect operators | N | **MERGE** (Represented in `/agents` table) |
| Unigreen Design Link | `console/src/routes/settings.tsx:86-95` | Navigate to design moodboards | N | **CUT** |

### 3.13 Design Panels (`/design` → Cut Page)

| Panel | File:Line | Operator Decision Supported | Helps Run/Verify | Verdict |
|---|---|---|---|---|
| Design Direction Picker | `console/src/routes/design.tsx:87-105` | Pick Unigreen theme | N | **CUT** (Does not run or verify jobs) |
| Wireframe Comparison Frames | `console/src/routes/design.tsx:196-218` | Render 520px design iframes | N | **CUT** |

### 3.14 Job Inspector Modal (`JobModal.tsx` & `JobDetailView.tsx`)

| Panel | File:Line | Operator Decision Supported | Helps Run/Verify | Verdict |
|---|---|---|---|---|
| Modal Chrome & Header | `console/src/features/jobs/JobDetailView.tsx:71-101` | Job ID, title, status, branch, timing | Y | **KEEP** (Cut duplicate top-bar ID; cut spend tokens) |
| Failure Explanation Alert | `console/src/features/jobs/JobDetailView.tsx:103-105` | Diagnose job failure reason | Y (Verify) | **KEEP** (Top of modal) |
| Run Timeline | `console/src/features/jobs/JobRunTimeline.tsx:30-117` | Detect hung or delayed phases | Y | **KEEP** |
| Artifact References | `console/src/features/jobs/JobDetailView.tsx:117-131` | Inspect produced code/diff artifacts | Y (Verify) | **KEEP** |
| Operational Thread | `console/src/features/messaging/OperationalThreadView.tsx` | Inject operator steering guidance | Y | **KEEP** (Collapsed by default) |
| Diagnostics & Repairs | `console/src/features/jobs/JobRealData.tsx:168-224` | Check repair count and verification history | Y (Verify) | **KEEP** (Inline counters into header) |
| Task List | `console/src/features/jobs/JobRealData.tsx:85-113` | Identify failed subtask | Y | **KEEP** (Absorbs Runs list) |
| Observations List | `console/src/features/jobs/JobRealData.tsx:139-162` | Agent-recorded evidence | Y (Verify) | **KEEP** (Collapsed by default) |
| Task Execution Backends | `console/src/features/execution/JobTaskExecution.tsx:18-74` | Check backend engine per task | Y | **KEEP** |
| Runtime Events & Trace | `console/src/features/jobs/JobDetailView.tsx:149-200` | Detailed trace log | Y (Verify) | **MERGE** (Link to `/events?jobId={id}`; show 50-row cap notice) |
| Token Spend Totals | `console/src/features/jobs/JobRealData.tsx:47-83` | Token accounting | N | **CUT** |

---

## 4. Places with Too Much Text

Spot audit of 29 verbose strings reveals 291 words reduced to 96 words in the compact redesign (67% reduction).

### 4.1 Repeated Disclaimers and Explanations

1. **Comms drafting limitations repeated across 4 locations (51 words total):**
   - `routes/comms.tsx:185`: "Ask the orchestrator to draft a brief. It can't start or merge anything." (13 words) → **CUT**
   - `routes/comms.tsx:190`: "Type a message to start a chat. Drafts are saved as Draft, never Ready." (14 words) → **CUT**
   - `features/comms/Composer.tsx:96`: "The orchestrator drafts briefs only. It cannot start, cancel or merge runs." (12 words) → **Shorten to:** "Drafts only. Cannot start or merge runs." (6 words)
   - `features/comms/ChatThread.tsx:6`: "Saved to LysStack/drafts as Draft. Only you can mark a brief Ready." (12 words repeated on every reply) → **Shorten to:** "Draft saved in LysStack." (4 words, render once in footer)

2. **Unreachable server notices repeated twice per page:**
   - Global `ConnectionBanner.tsx:25`: "CAN'T REACH HERMES · API {url} · last successful contact {time} · Retry" (12 words) → **KEEP**
   - Page-level `DataStates.tsx:38`: "{label} is not loading. Check that the Hermes runtime API is running at {url}." (14 words) → **Shorten to:** "Failed to load." (3 words)

3. **13 separate variations of "Hermes did not report" fallback strings:**
   - `features/agents/AgentDossier.tsx:23-26`: Four 8-10 word tooltips ("Hermes exposes no per-agent run list...", "Hermes does not report a live activity feed...", etc.) → **Replace with:** "—" with shared tooltip "Not reported by Hermes".
   - `routes/queue.tsx:12-13`: "Hermes exposes no estimator for queued or running work" (9 words) / "Hermes does not report a concurrency policy..." (10 words) → **Replace with:** "No estimator" / "No concurrency policy".
   - `features/jobs/JobRealData.tsx:196,202`: "Hermes did not report a repair count" (7 words) → **Replace with:** "—".

### 4.2 Subtitles and Empty States

| Location | Existing Copy | Words | Proposed Copy | Words |
|---|---|---|---|---|
| `routes/review.tsx:26` | Finished runs · merge after reading | 6 | Finished runs | 2 |
| `routes/floor.tsx:35` | Active jobs · by phase | 4 | (Cut; repeats stat label) | 0 |
| `routes/review.tsx:33` | No finished runs yet. A completed goal run appears here with its pull request. | 14 | No finished runs. | 3 |
| `routes/review.tsx:95` | Hermes could not open a pull request for this run | 10 | No PR opened | 3 |
| `routes/review.tsx:100` | No verifier verdict was recorded for this run. | 8 | No verdict recorded | 3 |
| `routes/execution.tsx:39` | MOCK FIXTURES · not live Hermes data. Start the Hermes runtime API to see real execution state. | 17 | (Cut; shell mock banner already states this) | 0 |
| `routes/index.tsx:90` | Nothing needs you right now. | 5 | Nothing needs attention. | 3 |
| `routes/events.tsx:186` | 2 new events · back to newest | 7 | 2 new ↑ | 3 |
| `features/messaging/OperationalThreadView.tsx:360` | Send operational guidance into job thread... | 6 | Send guidance… | 2 |
| `routes/queue.tsx:62-68` | Recoverable · 0 / No recoverable jobs | 6 | Recoverable (0) | 2 |

### 4.3 Duplicate Labels and Micro-Label Sprawl

- **Duplicate Token Label:** `JobDetailView.tsx:99` renders "tokens 1,234 tokens tracked". Cut duplicate; render "1,234 tokens".
- **Duplicate Job ID:** Modal top bar and modal header both print full job ID (`JobModal.tsx:28` & `JobDetailView.tsx:73`). Retain header ID only.
- **Duplicate Mock Banner:** `execution.tsx:39` renders second mock banner immediately below global shell banner. Cut route instance.
- **Micro-Label Clutter:** 180+ instances of `<=11px` uppercase labels with disparate tracking (`tracking-wide`, `tracking-wider`, `tracking-widest`). Replace with a single standard design token: `text-[11px] font-mono uppercase tracking-wider text-lys-muted`.

---

## 5. Layout Density

### 5.1 Overhead Chrome Compression

Existing console consumes ~150–220px of vertical space before rendering page content:
- Global Mock Banner: ~26px
- Unreachable Banner: ~40px
- Agent Breadcrumb Bar: 44px (agent routes only)
- PageHeader: ~150px sticky block (`pt-5 pb-4`, title row ~28px, divider line, and `min-h-[58px]` reserved stat strip).

**Redesign Rule:** Flatten `PageHeader` into a single 44px sticky bar containing title, freshness timestamp, and compact inline stat chips. Eliminated reserved 58px empty strip. Total overhead compressed from 150px to 44px, restoring >100px vertical viewport to operational data.

```
+---------------------------------------------------------------------------------------+
|  Queue  [ Backlog & History ]  ( updated 22:04:12 )      [3 RUNNING] [1 BLOCKED] [5 QUEUED] |
+---------------------------------------------------------------------------------------+
```

### 5.2 Padding and Nesting Stack Reduction

The existing UI nests padding 4–5 levels deep:
- Page container: `p-6 gap-6` (24px)
- Card container: `p-5` or `p-6` (20–24px)
- Inner section box: `p-3.5` (14px)
- Diagnostic item box: `p-2` (8px)
Result: Up to 70px of whitespace padding surrounding a 13px text value.

**Redesign Rule:**
- Page wrapper: `p-4 gap-3` (16px / 12px)
- Card container: `p-3` (12px)
- Inner boxes: Eliminate nested borders and padding; separate rows using 1px hairline dividers (`border-b border-lys-subtle/50`). Maximum nesting depth: 2 levels.

### 5.3 Fixed Dimensions and Viewport Squeezing

- **Floor Columns (`routes/floor.tsx:85`):** Hardcoded `w-64` (256px) forces horizontal scrolling on 5+ phase runs on standard 1080p laptop displays.  
  *Fix:* Use `min-w-[200px] flex-1` responsive column layout.
- **Agent Hero Card (`features/agents/AgentDossier.tsx:83`):** Fixed `min-h-[460px]` with a 120px decorative letter avatar wastes 50% of the screen.  
  *Fix:* Cut entire dossier page; table layout on `/agents` renders all data in dense rows.
- **Comms Viewport Offset (`routes/comms.tsx:139`):** Hardcoded `h-[calc(100vh-6rem)] min-h-[520px]` leaves artificial blank space.  
  *Fix:* Use `h-full flex-1` flexbox layout.
- **Dashboard Max Width (`routes/index.tsx:67`):** Hardcoded `max-w-5xl` creates empty wasted margins on 1440p+ widescreen monitors while all other pages are full width.  
  *Fix:* Make Dashboard full width with a responsive 2-column operational grid (`grid-cols-1 xl:grid-cols-2`).

### 5.4 Monolithic Modal Refactoring

`JobDetailView` stacks 10+ vertical sections inside a single 90vh scrolling container. Trace logs silently truncate at 50 rows.
*Fix:* Keep Header, Failure Alert, and Phase Timeline open at top. Place Tasks, Observations, Backend Execution, and Thread into dense accordion sections (`<details>` or collapsible panels). Provide direct link to `/events?jobId={id}` for full log streaming.

---

## 6. Visual Bugs and Broken States

1. **Unregistered Color Classes in `@theme` (`globals.css:9-34`):**
   `text-lys-status-danger`, `text-lys-status-warning`, `border-lys-status-danger`, and `bg-lys-surface-3` are used in `comms.tsx:161,180,197`, `ChatSidebar.tsx:55,59`, and `AgentModelSelector.tsx:261`, but are missing from Tailwind configuration. Alerts render as plain uncolored text.
2. **Review Card Ignores PR Lifecycle (`review.tsx:66,83-96`):**
   Renders "Open pull request" regardless of whether `prState` is `OPEN`, `MERGED`, or `CLOSED`. Merged runs appear active.
3. **Floor Job Header Status Always Green (`floor.tsx:125`):**
   Unconditionally uses `text-lys-success`, displaying green badges for `FAILED` and `BLOCKED` jobs.
4. **False "Nothing Needs You" on Dashboard Refresh Failure (`index.tsx:32,38-40`):**
   Reviews array defaults to `[]` when `useReviews()` fails or loads, clearing attention items and printing "Nothing needs you right now."
5. **Silent Stale State Retention (`floor.tsx:21,41,77`, `index.tsx:33,68`):**
   Failed API refreshes retain previous snapshot data without checking or displaying the `stale` boolean flag.
6. **Double Loading Spinner on Queue (`queue.tsx:42`, `MissionBoard.tsx:74`):**
   Identical loading states triggered simultaneously at route level and inside `MissionBoard`.
7. **Recoverable Jobs Keyboard Trap (`queue.tsx:82-95`):**
   `CopyId` nested within a `role="button"` div intercepts keyboard Enter events, preventing keyboard copying.
8. **Stale Rows Displayed Below Error Banner (`queue.tsx:79-81`):**
   Recoverable section renders full `ErrorState` banner while continuing to display cached job rows underneath.
9. **Usage Route Suppresses Capacity Load Failures (`usage.tsx:77-80,90-94,103-106`):**
   Header stat strip prints empty dashes on capacity load failure with no alert banner.
10. **Comms Sidebar Vanishes Below 768px (`comms.tsx:140`):**
    Sidebar is marked `hidden md:flex`, locking mobile users out of conversation switching and creation.
11. **Comms Asynchronous Response Race Condition (`comms.tsx:42-45,64-72`):**
    Unsynchronized promises allow slower responses from earlier chat selections to overwrite newer active chats.
12. **Comms Discards Composer Input on Error (`comms.tsx:53-61,68-74`):**
    Input text is cleared prior to confirmation of successful message dispatch.
13. **Comms Premature New-Chat Empty State (`comms.tsx:34-45,187-190`):**
    Displays "What should we plan?" new-chat prompt while existing conversations are actively fetching.
14. **Settings Page Layout Blowout and Mouse-Only Rows (`settings.tsx:20,25,65,71-74`):**
    `select-none` prevents copying; `min-w-[340px]` forces horizontal clipping on small screens; operator rows are unkeyboardable.
15. **Cell-Level Error Layout Destruction (`agents/index.tsx:101`, `DataStates.tsx:34`):**
    `ErrorState` component contains `m-4 p-4`, inflating table row height to >120px when an agent model save fails.
16. **Job Trace Blank During Initial Load (`JobDetailView.tsx:157-164`):**
    Lacks loading indicator; leaves blank panel while durable history events are fetching.
17. **Silent 50-Row Trace Log Cutoff (`JobDetailView.tsx:164`):**
    Hardcoded `traceRows.slice(0, 50)` gives no visual cue that trace events were truncated.
18. **Unchecked `displayName[0]` Crash Risk (`AgentPresence.tsx:27`, `AgentDossier.tsx:85`):**
    Direct array indexing crashes if `displayName` is empty or undefined.
19. **Unmemoized Sidebar Keyboard Listener (`Sidebar.tsx:90-99`):**
    Window event listener for `[` toggle key re-registers on every render cycle.
20. **Store-Wide 1Hz Re-Render Thrash (`useConsoleStore.ts:218-234`):**
    `tickClock` triggers store updates every 1,000ms; components using unselected store hooks re-render continuously.

---

## 7. Proposed Page Map

Compact 7-route operational architecture (plus 1 borderline route and 1 modal inspector). Eliminates `/agents/:agentId`, `/usage`, `/settings`, and `/design`.

```
OPERATOR CONSOLE
├── / (Dashboard)                    [Triage & active work: Attention list, Running runs, Health]
├── /queue (Queue)                   [Backlog & dispatch: Mission board, Filter chips, Recoverable]
├── /floor (Floor)                   [Live job monitoring: Dependency columns, Active phases, Checks]
├── /review (Review)                 [Job verification: PR approval, Verifier findings, Task chains]
├── /agents (Agents & Capacity)      [Runtime controls: Model & effort pickers, Quota meters, Reset timers]
├── /events (Events)                 [Forensics: Live event bus stream, Raw JSON inspector, Filters]
├── /execution (Execution)           [Backend infrastructure: Sandbox availability, Engine status]
├── /comms (Comms)                   [Borderline: Orchestrator brief drafting chat; drafts only]
└── OVERLAY: Job Inspector Modal     [Deep verification: Timeline, Tasks, Threads, Diagnostics]
```

### Route Optimization Summary
- **CUT `/agents/:agentId`**: Eliminated character bio cards, 120px letter portraits, and redundant model selectors.
- **MERGE `/usage` → `/agents`**: Integrated remaining capacity percentages, throttling flags, and reset countdowns directly into the agent model table.
- **CUT `/settings`**: Moved runtime version/uptime facts into Sidebar footer; moved operator list into `/agents`; eliminated unused 3D ambient toggle.
- **CUT `/design`**: Removed Unigreen aesthetic design boards (not an operational job concern).
- **CUT `DossierModal`**: Removed character artwork presentation modal.

---

## 8. ASCII Wireframes for Kept Pages

### 8.1 App Shell & Collapsible Sidebar

```
+----------------------------------------------------------------------------------------------------+
| HERMES // OPS   | [MOCK FIXTURES ACTIVE]                               | API: OK (34ms)  [REFRESH] |
+-----------------+----------------------------------------------------------------------------------+
| [=] COLLAPSE    | /PAGE TITLE                                      [INLINE STAT 1] [INLINE STAT 2] |
|                 +----------------------------------------------------------------------------------+
| TRIAGE          |                                                                                  |
|   Dashboard     |                                                                                  |
|                 |                                                                                  |
| JOBS            |                                                                                  |
|   Queue    [4]  |                                                                                  |
|   Floor    [1]  |                                 PAGE CONTENT AREA                                |
|   Review   [2]  |                                                                                  |
|                 |                                                                                  |
| SYSTEM          |                                                                                  |
|   Agents        |                                                                                  |
|   Events        |                                                                                  |
|   Execution [1] |                                                                                  |
|                 |                                                                                  |
| PLAN (BORDER)   |                                                                                  |
|   Comms         |                                                                                  |
|                 +----------------------------------------------------------------------------------+
| HERMES v0.4.12  | STALE NOTICE / BANNER (ONLY WHEN ACTIVE)                                         |
| HERDR  READY    |                                                                                  |
+-----------------+----------------------------------------------------------------------------------+
```

### 8.2 Dashboard (`/`)

```
+----------------------------------------------------------------------------------------------------+
| Dashboard  ·  Triage & Live Work               [3 RUNNING] [1 BLOCKED] [1 FAILED 24H] [2 TO REVIEW] |
+----------------------------------------------------------------------------------------------------+
| ATTENTION REQUIRED (2)                                                               (updated 22:04) |
| [!] FAILED   job_8f21c  fix-auth-token       Verifier check failed: test_refresh_token    [INSPECT] |
| [P] PAUSED   job_9a44b  refactor-db-pool     WAITING_FOR_CAPACITY (gemini resets in 14m)  [INSPECT] |
+----------------------------------------------------------------------------------------------------+
| RUNNING NOW (3)                                                                 [ALL ACTIVE FLOORS] |
| [*] job_4c11e  export-csv-worker      Phase: BUILDER (claude-3-7-sonnet)     Elapsed: 04m 12s      |
| [*] job_5d22f  cleanup-stale-cache    Phase: VERIFIER (codex)                Elapsed: 01m 45s      |
| [*] job_6e33a  update-api-docs        Phase: PLANNER (gemini-2.5-pro)        Elapsed: 00m 30s      |
+----------------------------------------------------------------------------------------------------+
| SYSTEM SNAPSHOT                                                                                    |
| Sandboxes: 4/4 Ready  ·  Event Stream: Connected (32 eps)  ·  Rate Limits: Normal (0 throttled)     |
+----------------------------------------------------------------------------------------------------+
```

### 8.3 Queue & Backlog (`/queue`)

```
+----------------------------------------------------------------------------------------------------+
| Queue  ·  Backlog & Recovery                   [Total: 12] [3 RUNNING] [1 BLOCKED] [8 QUEUED]      |
+----------------------------------------------------------------------------------------------------+
| FILTERS: [ALL (12)] [QUEUED (8)] [RUNNING (3)] [BLOCKED (1)] [FAILED (0)] [RECOVERABLE (2)]         |
+----------------------------------------------------------------------------------------------------+
| PRIO | JOB ID     | TITLE                      | REPO · BRANCH             | ASSIGNED | PROGRESS   |
|------+------------+----------------------------+---------------------------+----------+------------|
| P0   | job_4c11e  | export-csv-worker          | core · feat/csv-worker    | Claude   | 3/5 phases |
| P1   | job_9a44b  | refactor-db-pool           | backend · db/pool         | Gemini   | PAUSED     |
| P2   | job_7a88c  | add-healthcheck-endpoint   | api · chore/healthcheck   | —        | QUEUED     |
| P2   | job_8b99d  | migrate-user-schema        | backend · db/user-schema  | —        | QUEUED     |
| P3   | job_1c22e  | update-readme              | core · docs/readme        | —        | QUEUED     |
| RC   | job_3d44f  | sync-billing-webhook [REC] | billing · fix/webhook     | —        | STOPPED    |
+----------------------------------------------------------------------------------------------------+
```

### 8.4 Live Run Floor (`/floor`)

```
+----------------------------------------------------------------------------------------------------+
| Floor  ·  Active Job Execution                                        [1 ACTIVE JOB] (updated 22:04)|
+----------------------------------------------------------------------------------------------------+
| JOB: job_4c11e  export-csv-worker  [RUNNING] · Repairs: 1 · Worktree: /worktrees/run_4c11e         |
+----------------------------------------------------------------------------------------------------+
| DEPENDENCY COLUMNS (CARDS VIEW)                                                                    |
| +-------------------+  +-------------------+  +-------------------+  +-------------------+         |
| | 01. PLANNER       |  | 02. BUILDER       |  | 03. CHECK (FAIL)  |  | 04. REPAIR #1     |  [...]   |
| | Hermes Orchestr   |  | Claude 3.7 Sonnet |  | Antigravity (Test)|  | Codex             |         |
| | State: DONE       |  | State: DONE       |  | State: FAILED     |  | State: RUNNING    |         |
| | Time: 45s         |  | Time: 02m 10s     |  | Findings: 1 fail  |  | Time: 01m 15s     |         |
| | Plan created (5p) |  | 3 files generated |  | "assert 200==500" |  | Editing handler.py|         |
| +-------------------+  +-------------------+  +-------------------+  +-------------------+         |
+----------------------------------------------------------------------------------------------------+
```

### 8.5 Review & Verifications (`/review`)

```
+----------------------------------------------------------------------------------------------------+
| Review  ·  Completed Runs & Verifications                       [2 FINISHED RUNS] [2 WITH PR OPEN] |
+----------------------------------------------------------------------------------------------------+
| RUN: job_3a11b  add-stripe-webhook-handler               Repairs: 0  Finished: 12m ago  Cost: $0.42 |
| Branch: feat/stripe-webhook  ·  PR: #142 [OPEN]                                 [VIEW GITHUB PR ->]|
+----------------------------------------------------------------------------------------------------+
| VERIFICATION VERDICT: PASS (100% checks green)                                                     |
| Evaluator: Antigravity Verifier  ·  Checks: pytest unit (24/24), linter clean, sandbox build ok     |
| Task Chain: Planner (Hermes) -> Builder (Claude) -> Verifier (Antigravity)                         |
+----------------------------------------------------------------------------------------------------+
| RUN: job_2b99c  fix-session-race-condition               Repairs: 2  Finished: 45m ago  Cost: $1.15 |
| Branch: fix/session-race  ·  PR: #140 [MERGED]                                  [MERGED ON GITHUB] |
+----------------------------------------------------------------------------------------------------+
| VERIFICATION VERDICT: PASS AFTER REPAIR                                                            |
| Evaluator: Codex Verifier  ·  Findings: Initial deadlock resolved by mutex ordering in patch 2     |
| Task Chain: Builder (Claude) -> Check (FAIL) -> Repair (Codex) -> Re-check (PASS)                 |
+----------------------------------------------------------------------------------------------------+
```

### 8.6 Agents & Capacity (`/agents`)

```
+----------------------------------------------------------------------------------------------------+
| Agents  ·  Runtime Models & Capacity Allocation                    [3 AGENTS CONFIGURED] [0 STALL] |
+----------------------------------------------------------------------------------------------------+
| AGENT NAME  | PROVIDER  | CONFIGURED MODEL      | REASONING EFFORT | CAPACITY LEFT | RESET IN | ACT|
|-------------+-----------+-----------------------+------------------+---------------+----------+----|
| Claude      | Anthropic | claude-3-7-sonnet     | [high        v]  | 84% (420k tok)| 45m      |SAVE|
| Codex       | OpenAI    | o3-mini               | [medium      v]  | 92% (1.2m tok)| 1h 12m   |SAVE|
| Antigravity | Google    | gemini-2.5-pro        | [default     v]  | 12% [WARN]    | 08m 30s  |SAVE|
+----------------------------------------------------------------------------------------------------+
| Note: Model and reasoning updates apply to the next scheduled phase.                               |
+----------------------------------------------------------------------------------------------------+
```

### 8.7 Live Event Bus Stream (`/events`)

```
+----------------------------------------------------------------------------------------------------+
| Events  ·  Runtime Event Bus Log            [STREAM: CONNECTED] [0 FAILURES] [2 WARNINGS] (32 eps) |
+----------------------------------------------------------------------------------------------------+
| FILTERS: [SEVERITY: ALL v] [SOURCE: ALL v] [JOB ID: _________] [SEARCH TEXT: __________________]   |
+----------------------------------------------------------------------------------------------------+
| TIME     | SEVERITY | SOURCE      | KIND                 | DETAIL                     | JOB ID     |
|----------+----------+-------------+----------------------+----------------------------+------------|
| 22:04:15 | INFO     | herdr       | container.spawn      | worktree_4c11e created     | job_4c11e  |
| 22:04:12 | WARN     | hermes.llm  | rate_limit.warning   | gemini-pro quota at 88%    | job_9a44b  |
| 22:04:01 | INFO     | runner      | task.phase.start     | builder executing task 2   | job_4c11e  |
| 22:03:48 | INFO     | bus         | stream.heartbeat     | ping ack (12 clients)      | —          |
+----------------------------------------------------------------------------------------------------+
| [v] EXPAND RAW EVENT #41829: {"event": "container.spawn", "engine": "herdr", "status": "ok"}      |
+----------------------------------------------------------------------------------------------------+
```

### 8.8 Execution Sandboxes (`/execution`)

```
+----------------------------------------------------------------------------------------------------+
| Execution  ·  Backend Infrastructure Status                                   [2/2 ENGINES ONLINE] |
+----------------------------------------------------------------------------------------------------+
| BACKEND ENGINE | STATUS    | VERSION   | PATH / SOCKET          | ACTIVE SEATS | DETAIL            |
|----------------+-----------+-----------+------------------------+--------------+-------------------|
| Herdr CLI      | AVAILABLE | v1.8.2    | /usr/local/bin/herdr   | 3 running    | Linux cgroups v2  |
| Local Subproc  | AVAILABLE | system    | /bin/bash              | 1 running    | Isolated worktree |
+----------------------------------------------------------------------------------------------------+
| ACTIVE RUNTIME CONTAINERS (1)                                                                      |
| [cgroup-4c11e]  PID 29401  ·  CPU: 14%  ·  MEM: 210MB  ·  Job: job_4c11e (builder phase)           |
+----------------------------------------------------------------------------------------------------+
```

### 8.9 Brief Planner (`/comms` - Borderline View)

```
+----------------------------------------------------------------------------------------------------+
| Comms  ·  Orchestrator Planning Drafts                                       [DRAFTS ONLY · NO OP] |
+-----------------------+----------------------------------------------------------------------------+
| THREADS      [+ NEW]  | DRAFT: Add OAuth2 Refresh Rotation                                         |
| > OAuth2 Rotation     | Model: claude-3-7-sonnet  ·  Effort: high  ·  Context: 24%                 |
|   Stripe Webhook      +----------------------------------------------------------------------------+
|   Database Migration  | [User]: Draft a multi-phase implementation plan for refresh token rotation.|
|                       |                                                                            |
|                       | [Orchestrator]: Plan generated with 4 tasks: (1) schema, (2) token store,  |
|                       | (3) auth handler, (4) verifier tests. Draft saved to LysStack/drafts.      |
|                       +----------------------------------------------------------------------------+
|                       | [ > Enter message to orchestrator...                                     ] |
|                       | Drafts only. Orchestrator cannot start, modify, or merge runs.             |
+-----------------------+----------------------------------------------------------------------------+
```

### 8.10 Job Inspector Modal Overlay (`JobModal`)

```
+====================================================================================================+
| JOB INSPECTOR: job_4c11e  export-csv-worker                       [RUNNING]  [x] CLOSE (Esc)      |
| Repo: core · Branch: feat/csv-worker · Started: 22:00:03 (04m 12s elapsed) · Repairs: 1 · Replans: 0 |
+====================================================================================================+
| [!] FAILURE REASON (Phase 03 Check)                                                                |
| Test assertion error in test_csv_stream.py line 42: AssertionError: Expected 200 rows, received 0.  |
+----------------------------------------------------------------------------------------------------+
| RUN TIMELINE                                                                                       |
| [00:00] PLANNER ======> [00:45] BUILDER ============> [02:55] VERIFIER ===! [03:40] REPAIR =====>  |
+----------------------------------------------------------------------------------------------------+
| [v] TASK EXECUTION BREAKDOWN (4 tasks)                                                             |
|   - Task 1: Generate schema definition (Claude) ........................................ DONE (45s)|
|   - Task 2: Implement CSV writer stream (Claude) ...................................... DONE (130s)|
|   - Task 3: Unit test validation (Antigravity) ........................................ FAILED (45s)|
|   - Task 4: Fix null row buffering (Codex) ............................................ RUNNING    |
+----------------------------------------------------------------------------------------------------+
| [>] OPERATIONAL GUIDANCE THREAD (1 message)                                                        |
| [>] ARTIFACTS GENERATED (3 files: csv_writer.py, test_csv.py, patch_01.diff)                      |
| [>] DIAGNOSTICS & TRACE EVENTS (Showing 50 of 142 events)                       [OPEN IN EVENTS ->] |
+====================================================================================================+
```
