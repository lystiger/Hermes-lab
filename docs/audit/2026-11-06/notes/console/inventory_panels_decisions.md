# Console inventory: panels, decisions, verdicts

Date: 2026-11-06. Read-only audit of `console/src`. Paths are relative to the repo root; line numbers are from the files as they are in this worktree.

**Test check:** not run. The task said not to run tests or the project check. The HERMES project-check block asks for the check before finishing. The task instruction is the more specific one, so I followed it. The check still needs to be run by someone before merge.

**Rule used for verdicts:** a panel stays only if it helps an operator run a job (start it, see where it is, unblock it, decide on a model/limit) or verify one (read the result, the failure, the evidence, the PR). Everything else is cut, or merged into the panel that does that job.

Verdicts: **KEEP**, **MERGE → target**, **CUT**.

---

## 1. Routes

Source: `console/src/App.tsx:19-33`. Layout shell: `console/src/components/Layout.tsx`.

| Route | Page file | Operator decision | Helps run/verify | Verdict |
|---|---|---|---|---|
| `/` | `routes/index.tsx` | What needs me right now? | Y | KEEP |
| `/queue` | `routes/queue.tsx` | Which jobs are queued, blocked, failed? | Y | KEEP |
| `/review` | `routes/review.tsx` | Is this finished run right to merge? | Y (verify) | KEEP |
| `/floor` | `routes/floor.tsx` | Where is each live phase, and is a repair cycle stuck? | Y | KEEP (Cards view only) |
| `/events` | `routes/events.tsx` | What did the runtime do, and did it fail? | Y (verify) | KEEP |
| `/agents` | `routes/agents/index.tsx` | Which model/effort will the next phase use? | Y | KEEP, absorbs Usage and Settings operator list |
| `/agents/:agentId` | `routes/agents/$agentId.tsx` | (none beyond the `/agents` table) | N | CUT |
| `/usage` | `routes/usage.tsx` | Can an agent still take work (limits, resets)? | Y (capacity wait) | MERGE → `/agents` |
| `/execution` | `routes/execution.tsx` | Is each backend available to run work? | Y | KEEP, trimmed |
| `/comms` | `routes/comms.tsx` | Draft a brief that could become a run | Partly (drafts only) | KEEP, flagged borderline |
| `/settings` | `routes/settings.tsx` | Runtime facts, a no-op toggle, operator list | Partly | CUT page. Runtime facts → Sidebar footer. Operator list → `/agents` |
| `/design` | `routes/design.tsx` | Pick a Unigreen design direction | N | CUT (LysStack concern, not a job concern) |
| `*` | `App.tsx:31` | redirect to `/` | N | KEEP (plumbing) |

---

## 2. Panels, widgets and their verdicts

Columns: where it is (file:line) · operator decision it supports · helps run/verify · verdict.

### 2.1 Shell (every page)

| Panel | Where | Decision supported | Helps | Verdict |
|---|---|---|---|---|
| Mock-data banner | `Layout.tsx:26-30` | Am I looking at fixtures? | Y (trust) | KEEP. It is the only one; delete the copy in `routes/execution.tsx:37-41` |
| Connection banner (Hermes unreachable) | `components/ConnectionBanner.tsx:11-40` | Is the runtime reachable? Retry. | Y | KEEP, shorten copy |
| Header back-bar (agent pages only) | `components/Header.tsx:5-41`; returns null on other pages (`:24`) | Go back to `/agents` | N | CUT. Put a back link in the page header |
| Page header: title, subtitle, stat strip, sticky | `components/PageHeader.tsx:15-63` | Page identity and key numbers | Y (stat strip) | KEEP. Drop subtitles |
| Freshness ("updated HH:MM:SS") | `components/DataStates.tsx:92-96` | Is this data current? | Y (stale state) | KEEP |
| Unreported-metrics info tooltip | `components/NotReported.tsx:14-51`; used in `routes/queue.tsx:11-14`, `features/agents/AgentDossier.tsx:22-27,54` | Which numbers does Hermes not give? | N | CUT the prose. The header info icon has no run/verify value |
| Sidebar nav (10 items) | `components/Sidebar.tsx:28-54` | Navigate | Y | KEEP, reduce to 8 items (drop Usage, Settings; Design is not in the nav) |
| Sidebar nav badges: queue count, agents count, Events "live", Execution active count | `Sidebar.tsx:105-111` | Is there work waiting? | Y for queue and execution; N for agents count and "live" | KEEP queue and execution. CUT the "live" badge (a status, not a count). Agents count → CUT |
| Sidebar footer: Hermes and Herdr status | `Sidebar.tsx:197-223` (tooltip `:120-124`) | Is the runtime and its executor up? | Y | KEEP. Collapsed icon form stays |
| Sidebar collapse toggle and `[` key | `Sidebar.tsx:67-99,134-153` | Layout only | N | KEEP (small, already built); not worth more work |
| Mock banner duplicate on Execution | `routes/execution.tsx:37-41` | (duplicate) | N | CUT |

### 2.2 Dashboard `/` (`routes/index.tsx`)

| Panel | Where | Decision | Helps | Verdict |
|---|---|---|---|---|
| Stat strip: RUNNING, QUEUED, BLOCKED, FAILED 24H, TOKENS, TO REVIEW | `routes/index.tsx:42-61` | Is anything wrong or waiting? | Y for first five | MERGE: keep five; CUT TOKENS (spend, not run/verify) |
| Telemetry / job-queue error and stale notices | `routes/index.tsx:68-69` | Is this data trustworthy? | Y | KEEP |
| "Needs you" list (failed, blocked, paused, PR open) | `routes/index.tsx:86-134`; logic `features/overview/attention.ts` | What do I act on first? | Y | KEEP. Core panel |
| "Running now" list | `routes/index.tsx:136-166` | What is in flight? | Y | KEEP. Duplicates Floor at a coarser grain; that is fine on the dashboard |
| Agents summary list | `routes/index.tsx:168-188` | Which agents are there? | N (names and status only) | MERGE → `/agents`. Keep the count only if it fits |

### 2.3 Queue `/queue` (`routes/queue.tsx`, `features/jobs/MissionBoard.tsx`)

| Panel | Where | Decision | Helps | Verdict |
|---|---|---|---|---|
| Stat strip: RUNNING, BLOCKED, QUEUED, FAILED 24H | `routes/queue.tsx:21-28` | Backlog health | Y | MERGE into the MissionBoard header. The same four numbers appear on the dashboard |
| Unreported-metrics tooltip (time estimates, concurrency policy) | `routes/queue.tsx:11-14` | (none) | N | CUT |
| Duplicate loading line | `routes/queue.tsx:42` | (none) | N | CUT (MissionBoard already shows loading, see `MissionBoard.tsx:74`) |
| Mission board: status columns, empty-status chip row | `features/jobs/MissionBoard.tsx:39-118` (chips `:99-113`) | Which statuses hold work? | Y | KEEP. Keep chips as one compact row |
| Job card: priority, title (opens inspector), repo · branch, "assigned", "started", progress | `MissionBoard.tsx:120-182` | Which job, which branch, is it moving? | Y | KEEP title, priority, branch, assigned, progress. CUT "started" (the list is ordered and the inspector shows it). CUT the "progress —" placeholder row when unknown |
| Per-card copy-ID control | `MissionBoard.tsx:139` (`components/CopyId.tsx`) | Copy an ID | N in a list | CUT from cards. Keep in the inspector |
| MISSION INTERRUPTED note on FAILED cards | `MissionBoard.tsx:173-177` | Is this failed? | Y (same info as the status column) | MERGE: the column already says it. Keep text short or drop |
| Recoverable jobs card | `routes/queue.tsx:59-104` | Which jobs could be recovered? | Partly; the card says "read-only", so there is no action | MERGE into the board as a filter pill. Fix the nested-control bug (see §4) |
| Empty "Recoverable · 0" bar | `routes/queue.tsx:62-68` | (none) | N | CUT with the card |

### 2.4 Review `/review` (`routes/review.tsx`)

| Panel | Where | Decision | Helps | Verdict |
|---|---|---|---|---|
| Subtitle "Finished runs · merge after reading" | `routes/review.tsx:26` | Reminder: a human merges | Y, but long | KEEP as a short line |
| Stat strip: FINISHED RUNS, WITH A PR | `routes/review.tsx:19-22` | Review backlog | Y | KEEP |
| Review card: goal headline | `review.tsx:55-56` | Which run? | Y | KEEP |
| Meta row: Branch, Repairs, Cost, Finished | `review.tsx:57-64` | Is this run clean and cheap enough to merge? | Y (repairs, branch). Cost is borderline | KEEP Branch, Repairs, Finished. Cost stays here only (the review decision) |
| PR link ("Open pull request" / "No pull request") | `review.tsx:83-96` | Open the PR and read it | Y | KEEP. It must show the PR state (see §4) |
| Verification block (verdict summary, findings, verifier task) | `review.tsx:98-118` | Did the verifier pass? | Y (verify) | KEEP. Core |
| Task chain (role → agent, replaced checks dimmed) | `review.tsx:121-142` | Who did each step, and what got replaced? | Y (verify) | KEEP |
| Empty-state sentence | `review.tsx:32-34` | (none) | N | Shorten to one line |
| "No verifier verdict was recorded for this run." | `review.tsx:100` | Verdict missing | Y (verify) | KEEP, shorten |

### 2.5 Floor `/floor` (`routes/floor.tsx`, `features/floor/FloorCard.tsx`)

| Panel | Where | Decision | Helps | Verdict |
|---|---|---|---|---|
| Stat strip: ACTIVE JOBS | `routes/floor.tsx:28` | How many are live | Y | KEEP (one number, can be in subtitle) |
| One section per active job | `routes/floor.tsx:51-102` | Where is each phase? | Y | KEEP |
| Job header: title, status, repair-cycle count | `routes/floor.tsx:121-132` | Is it in a repair loop? | Y | KEEP title, repair count. Status colour is wrong (see §4) |
| Job header: spend ("no usage yet") | `routes/floor.tsx:70,133` | Spend | N | CUT |
| Cards / Timeline toggle | `routes/floor.tsx:135-149` | Two views of the same phases | Y, but duplicated | CUT the Timeline view. The job inspector already has the timeline (`features/jobs/JobRunTimeline.tsx`) |
| Freshness | `routes/floor.tsx:134` | Current? | Y | KEEP |
| Phase card: role, chain label (Repair / Re-check N), state, agent mark, name | `features/floor/FloorCard.tsx:42-99` | Which phase, which agent, what state? | Y | KEEP |
| Phase card: elapsed time | `FloorCard.tsx:81-82` | Is it stuck? | Y | KEEP |
| Phase card: cost | `FloorCard.tsx:47,83` | Spend | N | CUT |
| Phase card: latest event line | `FloorCard.tsx:89-91` | What is it doing now? | Y | KEEP, one line |
| Phase card: findings list and "+N more" (failed or replaced checks) | `FloorCard.tsx:101-114` | Why did the check fail and what replaced it? | Y (verify, repair chain) | KEEP. It is the repair chain's evidence |
| "Replaced by …" line | `FloorCard.tsx:94-96` | Which check superseded this one? | Y | KEEP |

### 2.6 Events `/events` (`routes/events.tsx`)

| Panel | Where | Decision | Helps | Verdict |
|---|---|---|---|---|
| Stat strip: EVENTS HELD, FAILURES, WARNINGS, STREAM | `routes/events.tsx:89-94` | Did something fail? Is the stream live? | Y (FAILURES, WARNINGS, STREAM). EVENTS HELD is not | MERGE: keep FAILURES, WARNINGS, STREAM. CUT EVENTS HELD |
| Category and source filter pills | `events.tsx:73-85,110-112` | Narrow to failures or one source | Y | KEEP. Cap the source list (it is unbounded) |
| "N of M shown" | `events.tsx:114` | (none) | N | Shorten |
| Column header row | `events.tsx:117-124` | Read columns | Y | KEEP |
| Event row: time, severity, source, kind, detail, job/run | `events.tsx:130-157` | What happened? | Y | KEEP |
| Expanded row: raw JSON dump | `events.tsx:159-171` | Verify the raw event | Y (verify) | KEEP, collapsed by default |
| "N new events · back to newest" pill and scroll freeze | `events.tsx:28-51,179-189` | Read without the list jumping | Y | KEEP |

### 2.7 Execution `/execution` (`routes/execution.tsx`)

| Panel | Where | Decision | Helps | Verdict |
|---|---|---|---|---|
| Stat strip: BACKENDS AVAILABLE | `routes/execution.tsx:19-21` | Can work run at all? | Y | KEEP |
| Refresh button | `routes/execution.tsx:31-33` | Re-read the snapshot | Y | KEEP |
| Backend cards (name, available/unavailable, detail) | `routes/execution.tsx:56-71` | Which backend is up, and why not? | Y | KEEP, trimmed (detail one line) |
| "Recent execution timeline" card | `routes/execution.tsx:74-82` | What did the backends do? | Partly; same events are in Events | MERGE → `/events` (filter on execution events) |
| `ExecutionBackendStrip`, `ExecutionResourceCard`, `ActiveExecutionCard` | `features/execution/ExecutionBackendStrip.tsx`, `ExecutionResourceCard.tsx`, `features/jobs/ActiveExecutionCard.tsx` | Resource (seat, pane, process) state | Would be Y | CUT. No page mounts them. `ExecutionResourceCard` is used by tests only, so the resource view is not on any page |

### 2.8 Comms `/comms` (`routes/comms.tsx`, `features/comms/*`)

Borderline: the orchestrator drafts briefs and cannot start or merge runs. A brief can become a run, so I keep the page as the planning entry. The owner should confirm.

| Panel | Where | Decision | Helps | Verdict |
|---|---|---|---|---|
| Chat list: new, select, rename, delete | `features/comms/ChatSidebar.tsx:17-84`; `routes/comms.tsx:140-149` | Pick or start a brief thread | Partly | KEEP. Visible only at `md` and up (see §4) |
| Model select | `routes/comms.tsx:156-159` | Model that drafts the brief | N for runs | MERGE into one compact control row |
| Effort select | `routes/comms.tsx:171-176` | Reasoning effort for the brief | N for runs | MERGE with model |
| Context meter (tokens, % full) | `routes/comms.tsx:160-165`; `features/comms/contextUsage.ts` | Is the chat getting expensive? | N | CUT |
| "Earlier messages summarized" | `routes/comms.tsx:166` | (none) | N | CUT |
| Compact button (header) | `routes/comms.tsx:167-170` | Shrink the chat | N | KEEP only as one control. It appears twice today |
| Context-full banner with Compact button | `routes/comms.tsx:196-206` | (nudge) | N | CUT |
| Empty-state copy (two variants) | `routes/comms.tsx:182-191` | Start a brief | Partly | MERGE into one line |
| Error alert | `routes/comms.tsx:180` | Request failed | Y | KEEP (colour bug, see §4) |
| Message thread, copy-reply | `features/comms/ChatThread.tsx:17-62` | Read the draft | Y | KEEP |
| Draft note under each saved draft | `ChatThread.tsx:6,48-53` | Where the draft went | Y | MERGE: short "Draft saved: <name>" only; the full note repeats per message |
| Busy indicator | `ChatThread.tsx:57-61` | Waiting for reply | Y | KEEP |
| Composer and footnote | `features/comms/Composer.tsx:13-37` (footnote `:35`) | Send a message | Y | KEEP. Footnote shortens to "Drafts only. Cannot start or merge runs." |

### 2.9 Usage `/usage` (`routes/usage.tsx`) → merged into Agents

| Panel | Where | Decision | Helps | Verdict |
|---|---|---|---|---|
| Stat strip: TOKENS, REQUESTS, SUCCESS RATE, THROTTLING (one shared tooltip on all four) | `routes/usage.tsx:88-95` | Spend and reliability | THROTTLING: Y (explains WAITING_FOR_CAPACITY). Others: N | MERGE: keep THROTTLING. CUT TOKENS, REQUESTS, SUCCESS RATE |
| Per-agent limit card: name, plan, badge, left %, reset time, windows | `routes/usage.tsx:25-73` | Can this agent still take work, and when does it reset? | Y | MERGE into the Agents table as one column (left % and reset) |
| Not-ready auth help text | `routes/usage.tsx:69` | How to fix the agent's login | Y (unblocks a run) | KEEP, shown only when not ready |
| Empty and loading states | `routes/usage.tsx:105-115` | (none) | N | Keep the states, short copy |

### 2.10 Agents

#### `/agents` table (`routes/agents/index.tsx`)

| Panel | Where | Decision | Helps | Verdict |
|---|---|---|---|---|
| Agent table: name, provider, model select, reasoning select, Save | `routes/agents/index.tsx:24-105,127-143` | Which model and effort will the next phase use? | Y | KEEP. This is the one model editor |
| Inline save error inside a table cell | `routes/agents/index.tsx:101` | Save failed | Y | KEEP, but see the spacing bug in §4 |
| Stat count "agents" | `routes/agents/index.tsx:112` | (none) | N | CUT |
| Limit column (from Usage) | (new) | Can this agent take work? | Y | ADD, from `routes/usage.tsx:25-73` |
| Operator list from Settings | `routes/settings.tsx:64-83` | (duplicate) | N | MERGE here (the table is the list) |

#### `/agents/:agentId` (`features/agents/*`)

| Panel | Where | Decision | Helps | Verdict |
|---|---|---|---|---|
| Roster list with status filter | `features/agents/AgentRoster.tsx:32-60` | Pick an agent | N (the table does this) | CUT |
| Agent presence card (initial mark, name, status, current task) | `features/agents/AgentPresence.tsx:11-56` | Identity | N | CUT. Current task moves to a table column |
| "Running now · by role" strip | `features/agents/RunningPhasesStrip.tsx:15-61` | Who runs which role right now | Y, but duplicates Floor | CUT (Floor has it per phase) |
| Dossier header: name, status, model, provider, copy ID | `features/agents/AgentDossier.tsx:40-52` | Identity | Partly | MERGE: status and current task only |
| "Dispatch" button | `AgentDossier.tsx:56-64` | Dispatch a task | N. Disabled. The title says the API has no command endpoint | CUT. Dead control |
| Details toggle | `AgentDossier.tsx:65-76` | Hide and show specs | N | CUT |
| 120px initial-letter portrait | `AgentDossier.tsx:83-87` | (decoration) | N | CUT |
| Specs: provider, model, focus, current task, active tool | `AgentDossier.tsx:91-99` | What is the agent doing? | Y for current task and active tool; N for the rest | KEEP current task and active tool, as table columns. CUT provider, model (already in table), focus |
| Capabilities chips | `AgentDossier.tsx:100-112` | (none) | N | CUT |
| Model configuration card (configured vs last used, selects, Save) | `features/agents/AgentModelSelector.tsx:26-271` | Change model and effort | Y | CUT. It duplicates the `/agents` table editor (two Save buttons for one setting). Keep the table. Its "Applies to the next phase" line (`:250-253`) moves to the table header |
| Context meter | `features/agents/AgentContextMeter.tsx:5-67` | Agent context fill | N for runs as far as I can tell | CUT. Not read in full; revisit only if Hermes reports context per agent for the next phase |
| Character-card dossier modal | `components/DossierModal.tsx:6-59` (imported at `Layout.tsx:6` and mounted there) | (decoration) | N | CUT. Nothing calls `setActiveDossierAgent` outside this file, so it cannot open |

### 2.11 Settings `/settings` (`routes/settings.tsx`)

| Panel | Where | Decision | Helps | Verdict |
|---|---|---|---|---|
| Runtime & environment facts | `routes/settings.tsx:23-36` | Which runtime am I on? | Y, rarely | MERGE → Sidebar footer tooltip (already shows service, version, uptime, `Sidebar.tsx:120-124`) |
| Motion (system setting, read-only) | `routes/settings.tsx:45-48` | (none) | N | CUT |
| "3D Ambient Rings & Perspective" toggle | `routes/settings.tsx:50-58` | (none) | N. It does nothing | CUT. `AmbientGyro` is never mounted; the store flag `ambient3d` only feeds this toggle |
| Registered operators list (click to open agent) | `routes/settings.tsx:64-83` | Which agents exist | N | MERGE → `/agents` table |
| Projects → Unigreen design boards link | `routes/settings.tsx:86-95` | (none) | N | CUT |
| Footer "Operators come from Hermes (GET /agents)" | `routes/settings.tsx:97-99` | (developer note) | N | CUT |

### 2.12 Design `/design` (`routes/design.tsx`)

| Panel | Where | Decision | Helps | Verdict |
|---|---|---|---|---|
| Direction picker, reason box, POST to `/design/unigreen/decision` | `routes/design.tsx:87-105,142-185` | Choose a Unigreen design direction | N for Hermes jobs | CUT. It writes a human decision for LysStack, not for a run |
| Wireframe iframes (520px each) and comparison sheet | `routes/design.tsx:196-218` | Look at the boards | N | CUT with the page |

### 2.13 Job inspector (modal) `components/JobModal.tsx` → `features/jobs/JobDetailView.tsx`

This is the deepest decision surface. It opens from any job row.

| Panel | Where | Decision | Helps | Verdict |
|---|---|---|---|---|
| Modal chrome: "LYSCONTROL // JOB INSPECTOR", id, CLOSE | `components/JobModal.tsx:23-36` | Close | N | KEEP the close control. Chrome text → just the job ID |
| Header: id, title, status, repo, branch, started, completed, elapsed | `features/jobs/JobDetailView.tsx:71-101` | Which job, what state, how long? | Y | KEEP id, title, status, branch, started, elapsed. CUT "completed —" for running jobs |
| Header: tokens | `JobDetailView.tsx:99` | Spend | N | CUT |
| Failure explanation (role=alert) | `JobDetailView.tsx:103-105`; `features/jobs/JobRealData.tsx:31-44` | Why did it fail? | Y (verify) | KEEP. Top of the inspector |
| Run timeline (phases on one time axis) | `JobDetailView.tsx:107-112`; `features/jobs/JobRunTimeline.tsx:30-117` | Where did time go? Which phase is stuck? | Y | KEEP |
| Artifact references | `JobDetailView.tsx:117-131` | Which outputs exist? | Y (verify) | KEEP |
| Operational thread: messages, reply, operator guidance box, DISPATCH | `JobDetailView.tsx:136-139`; `features/messaging/OperationalThreadView.tsx` (form `:320-370`, artifact modal `:388-420`) | Send guidance into a live job | Y | KEEP, collapsed by default. Artifact metadata modal → MERGE into the artifact list |
| Diagnostics: verification, repairs, replans, retry history | `JobDetailView.tsx:141`; `JobRealData.tsx:168-224` | Did verification run? How many repairs? | Y (verify) | KEEP. Move repair and replan counts into the header |
| Tasks list (role, status, attempt, error) | `JobDetailView.tsx:142`; `JobRealData.tsx:85-113` | Which task failed and why? | Y | KEEP |
| Runs list | `JobDetailView.tsx:143`; `JobRealData.tsx:115-137` | Which runs belong to which task? | Partly; overlaps Tasks | MERGE into Tasks |
| Observations list | `JobDetailView.tsx:144`; `JobRealData.tsx:139-162` | Agent-reported findings | Y (verify), often empty | KEEP, collapsed by default |
| Task execution: backend and resource badges per task | `JobDetailView.tsx:147`; `features/execution/JobTaskExecution.tsx:18-74` | Which backend ran each task? | Y | KEEP |
| Runtime events and traces (last 50 rows) | `JobDetailView.tsx:149-200` | Raw events for this job | Y, but duplicates Events | MERGE → a "Open in Events" link filtered by job ID. Note: the list is cut at 50 rows with no notice (see §4) |
| Job token totals | `JobRealData.tsx:47-83` | Spend | N | CUT (the stale-state logic is well built; the panel is not needed) |

---

## 3. Cross-page duplicates driving the merge verdicts

| Duplicated thing | Where it appears today |
|---|---|
| Running / queued / blocked / failed counts | Dashboard strip, Queue strip, Floor header, Sidebar badges |
| Running work | Dashboard "Running now", Floor, `RunningPhasesStrip` on `/agents/:id` |
| Agent list | Dashboard summary, Settings operators, `/agents` table, `/agents/:id` roster, Sidebar count |
| Model and effort editor | `/agents` table row and `AgentModelSelector` on `/agents/:id` (two Save buttons, same setting) |
| Execution events | Events log, Execution "recent timeline", job inspector trace |
| Spend and tokens | Dashboard, Floor header, Floor cards, job header, Usage, Review, Comms meter |
| Loading message on Queue | `routes/queue.tsx:42` and `MissionBoard.tsx:74` |
| Mock banner | `Layout.tsx:26-30` and `routes/execution.tsx:37-41` |
| Compact control | `routes/comms.tsx:167` and `:203` |

---

## 4. Other things noticed while reading (handed to the visual-bugs task; not audited here)

Each is from reading the code; none was run in a browser.

- `text-lys-status-danger`, `text-lys-status-warning`, `border-lys-status-danger` and `bg-lys-surface-3` are not defined in the `@theme` block (`console/src/styles/globals.css:9-34`). They match no token and are silently dropped. Uses: `routes/comms.tsx:161,180,197`, `features/comms/ChatSidebar.tsx:55,59`, `routes/design.tsx:111,175`, `features/agents/AgentModelSelector.tsx:261`.
- The Review card shows "Open pull request" for any `prUrl`. `prState` (OPEN / MERGED / CLOSED) is never rendered (`routes/review.tsx:66,83-96`). A merged PR looks like one that still needs review. Only `features/overview/attention.ts:49` and the dashboard count use OPEN.
- The Floor job header status is always `text-lys-success`, whatever the status (`routes/floor.tsx:125`). A FAILED or BLOCKED job reads green.
- The Comms conversation list is `hidden md:flex` (`routes/comms.tsx:140`). Below `md` there is no list and no "New chat". Chats cannot be switched or created on a narrow window.
- In the Recoverable jobs row, a copy button (`CopyId`) sits inside a `role="button"` div (`routes/queue.tsx:82-95`). Pressing Enter on the copy button hits the row's keydown handler, which calls `preventDefault` and opens the job. Copy cannot be reached from the keyboard.
- The Dashboard "Agents" section shows a heading with a count and an empty list when there are no agents, and no empty message (`routes/index.tsx:168-188`).
- Settings sets `select-none` on the whole page (`routes/settings.tsx:20`), so model names and runtime values cannot be selected or copied. The operator rows are clickable `div`s with no keyboard access (`:70-75`).
- `ErrorState` has `m-4 p-4` (`components/DataStates.tsx:34`). It sits inside a table cell on `/agents` (`routes/agents/index.tsx:101`) and inflates the row.
- The inspector trace list is hard-capped at 50 rows with no "showing 50 of N" note (`features/jobs/JobDetailView.tsx:164`).
- Dead code with zero live importers, outside tests: `components/AmbientGyro.tsx`, `components/AnimatedCube.tsx`, `features/execution/ExecutionBackendStrip.tsx`, `features/jobs/ActiveExecutionCard.tsx`, `features/tools/ToolCallItem.tsx`. Used only by tests (or only by dead code): `features/execution/ExecutionResourceCard.tsx`, `features/jobs/QueueTable.tsx`, `features/telemetry/UsageMeters.tsx`, `features/telemetry/ProviderTelemetryList.tsx`, `features/agents/AgentLaneCard.tsx`, `features/agents/AgentPortrait.tsx`.
- Performance, not visual: 11 components call `useConsoleStore()` with no selector. The store's `tickClock` writes every second (`stores/useConsoleStore.ts:218-234`), so each of them re-renders once a second. The Sidebar's `[` key listener is re-bound on every render (`Sidebar.tsx:90-99`, no dependency array).
- Possible key-casing mismatch, not reproduced: `AgentModelSelector.tsx:29` looks up `models[agentId.toLowerCase()]`; the table looks up `models?.[agent.id]` (`routes/agents/index.tsx:140`). If Hermes ever returns mixed-case IDs, one view shows a model and the other shows "No models".
- Text size: about 49 occurrences of `text-[9px]` to `text-[10px]` and about 180 at `text-[11px]` or below, across `console/src` excluding tests (grep count).

---

## 5. Summary of counts

- Routes: 13 declared, including the `*` redirect. Kept: `/`, `/queue`, `/review`, `/floor`, `/events`, `/agents`, `/execution`, `/comms` (8). Merged: `/usage`. Cut: `/settings`, `/design`, `/agents/:agentId`.
- Panels: every panel on the pages above has a row in §2. The verdict count is not tallied.
- Read in full: all routes, `App.tsx`, `Layout.tsx`, `Sidebar.tsx`, `Header.tsx`, `ConnectionBanner.tsx`, `PageHeader.tsx`, `DataStates.tsx`, `NotReported.tsx`, `JobModal.tsx`, `DossierModal.tsx`, `CopyId.tsx`, `FilterPills.tsx`, `Card.tsx`, `MissionBoard.tsx`, `JobDetailView.tsx`, `JobRealData.tsx`, `JobRunTimeline.tsx`, `JobTaskExecution.tsx`, `ExecutionTimeline.tsx`, `FloorCard.tsx`, `ChatSidebar.tsx`, `ChatThread.tsx`, `Composer.tsx`, `AgentWorkspace.tsx`, `AgentDossier.tsx`, `AgentRoster.tsx`, `AgentPresence.tsx`, `RunningPhasesStrip.tsx`, `AgentModelSelector.tsx`.
- Read in part: `api/hooks.ts` (lines 1-120 and 230-250, plus the export list), `globals.css` (the `@theme` block and the keyframe list), `OperationalThreadView.tsx` (lines 1-60, 230-300 and 330-420, plus grep hits), `AgentContextMeter.tsx` (first 12 lines), `contextUsage.ts` (grep hits), `ExecutionBackendStrip.tsx` (head), `UsageMeters.tsx` (head), `ProviderTelemetryList.tsx` (head), `ExecutionResourceCard.tsx` (head), `ActiveExecutionCard.tsx` (head), `QueueTable.tsx` (head), `AgentLaneCard.tsx` (head), `ToolCallItem.tsx` and `AmbientGyro.tsx` (head). Verdicts on the parts not read in full rest on the importer grep and those headers.
- Not opened: `features/comms/Markdown.tsx`, `AnimatedCube.tsx`, `CyberButton.tsx`.
- Not done: no browser run, no screenshots, no test or project-check run.
