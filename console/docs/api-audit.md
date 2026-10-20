# LysControl API truth audit

Audited 2026-10-14, approximately 07:35–07:38 UTC, against `http://localhost:8000`, LysControl HEAD `5ff0a6e`, and the checked-out Hermes implementation in `/home/lystiger/Projects/Hermes-lab`. This is an observation of the running service, not a guarantee that its runtime state matches every checkout. Only curl GET requests were made; no mutations, `/internal/*` requests, or rig commands were run. Only this document was written.

## Classification and mode

- **REAL:** the HTTP adapter retrieves actual API data, including explicitly described derivations. This does not mean every field in the resulting view is real.
- **HARDCODED:** static values or unsupported/empty results returned or displayed in HTTP mode. Honest `—`/unavailable placeholders are distinguished from fabricated measurements below.
- **MOCK:** available only from the mock adapter; not a real integration.
- **DEAD:** no production UI consumer, even if an adapter method implements an endpoint. Tests are not UI consumers.

`src/api/client.ts:5` selects HTTP mode only when `VITE_LYSSTACK_API_URL` is truthy. Otherwise the application uses `MockHermesApi`, including seeded jobs, agents, messages, quotas, execution snapshots, and generated events. A working localhost API does not automatically select HTTP mode. All REAL classifications below assume HTTP mode.

## Live GET evidence

`J = run_20261014_140653_live-runner-e2e`; `T = thread_job_run_20261014_140653_live-runner-e2e`. These IDs were discovered from live responses, not invented. Requests used `curl -sS --max-time 10 -w '\n%{http_code}'`; the stream used `-N --max-time 2`.

| Request | HTTP | Actual observation / type check |
|---|---|---|
| `/health` | 200 | `status: "ok"`, `service: "hermes"`, `version: "0.1.0"`, numeric `uptimeSeconds`, ISO `timestamp`; matches HealthStatus. |
| `/agents` | 200 | Three registered agents: gemini, claude, codex; all IDLE. Identity, provider, model, role, capabilities, phase, persona and presentation supplied. `currentTask`, `activeTool`, `presentation.characterCardUrl`, and `persona.systemPromptFragment` were null. No context, session-token, queue-depth, activity, allowance, or run-history measurements. |
| `/jobs` | 200 | One FAILED job J, progress 0.5, two phases in detail. Summary includes `blockedReason`, `repairCount`, `replanCount`; adapter drops these summary fields. |
| `/jobs?status=RUNNING`, `/threads?jobId=J` | 200 each | Empty active-job list; job-scoped thread filter returns T. Confirms the Overview's RUNNING banner is not backed by an active job. |
| `/jobs/J` | 200 | Two phases, tasks/observations/artifacts/retryHistory empty, verification null, one real test failure in errors. Phase timestamps/duration/detail contain nulls. Includes phase dependencies/requiredCapabilities absent from frontend types. |
| `/jobs/J/tasks`, `/jobs/J/runs`, `/jobs/J/observations` | 200 each | Empty arrays. These endpoints work, but populated record schemas were not empirically verified. |
| `/jobs/J/events?limit=5` | 200 | Event envelope matches `/events`, including `runId`, `actorId`, nullable `taskId`, and metadata. |
| `/jobs/J/telemetry` | 200 | `{job_id: J, tokens: {input_tokens: 0, output_tokens: 0, cached_tokens: 0, total_tokens: 0}}`. No spend, budget limit, per-agent breakdown, or projections. |
| `/jobs/J/recovery` | **404** | `Job 'J' not found in event store`, despite J being available through `/jobs/J`. Historical runner visibility is not necessarily durable reactive recovery state. |
| `/jobs/recoverable` | **404** | `Job 'recoverable' not found`. The earlier `/jobs/{job_id}` route shadows this static route (Hermes `main.py:338`, `main.py:455`). This is a reachable backend routing defect. |
| `/capacity/telemetry` | 200 | `{timestamp, summary, providers: {}, jobs_tracked: 0}`. Summary contains zero provider/request/failure/throttling/input/output/cached/total token counts. This is measured registry emptiness, not a confirmed zero daily bill or provider quota. |
| `/threads` | 200 | One thread T, actual title/jobId/timestamps and participant refs. Claude appears twice in participants; duplicate comes from API, not adapter. |
| `/threads/T` | 200 | Same metadata as list row. |
| `/threads/T/messages?limit=5` | 200 | Two handoffs, conversationId/intent/phaseId, null replyTo/correlationId, commit and handoff artifact refs with trust metadata. Mapping preserves the message fields. |
| `/agents/claude/inbox?limit=3` | 200 | One ACKNOWLEDGED entry with embedded handoff message and acknowledgedAt. |
| `/agents/gemini/inbox?limit=3`, `/agents/codex/inbox?limit=3` | 200 each | Empty arrays. |
| `/events?limit=5` | 200 | Runtime event envelope uses numeric epoch-second rawTs, display ts, dur, jobId/taskId/runId/actorId, metadata. Last event was OpenRig resource release attributed to task write_two and actor claude. |
| `/events/stream?after=evt_1791961678984_0032` | 200 | Replayed next event as `id: …`, `event: trace`, JSON `data: …`. Curl exit 28 after two seconds was the deliberate observation timeout, not endpoint failure. |
| `/execution` | 200 | Three backend availability rows; resources empty; OpenRig daemon up, ledger owners 0/rigIds []; numeric takenAt. Snapshot mapping matches observed fields. Populated resource mapping assessed against D-009 and registry code, not a live occupied seat. |
| `/ready`, `/version`, `/info`, `/metrics` | 200 each | Respectively readiness, version, environment/name, and numeric uptime_seconds/requests_handled. No dedicated UI consumers. |

No 5xx or transport errors occurred in these probes. Mutating methods were inspected in source only; no successful action execution is claimed.

## Every HTTP adapter method

Line references are in `src/api/adapters/httpAdapter.ts`. Mixed methods are split by field or action rather than classifying fabricated fields as real.

| Method / line | Status | Endpoint / source | Production consumers and limits |
|---|---|---|---|
| constructor:68 | HARDCODED configuration | Default localhost URL; selected URL from client environment | All methods; not server-discovered configuration. |
| getHealth:74 | REAL | GET `/health` | Layout → useEventStream → store → Header connection tooltip. Standalone useHealth hook is unused. |
| getAgents:82 | REAL identity/status; HARDCODED fallbacks | GET `/agents` | Overview lanes, Agents list/detail, Header, Settings operators, Queue actor labels, dispatch recipient lists, portraits/dossier. No usage fields are returned. |
| getAgent:118 | REAL base identity; HARDCODED detail | Calls getAgents; no `/agents/{id}` detail route | Agent detail and Header. Input/output/cache/remaining `—`, percentages `0%`, activity/runs empty, one STATUS metric, quota unavailable, capacity/reset placeholders. Detailed metrics exist only in MOCK mode. |
| getJobs:152 | REAL core; HARDCODED estimates/policy | GET `/jobs?status=…` | Overview queue, QueueTable, QueueRoute, pipeline and telemetry derivations. Default server limit 50; no pagination. |
| getJob:183 | REAL phases/tasks/observations/artifacts/errors; HARDCODED additional detail | GET `/jobs/{id}` | JobModal → JobDetailView; getPipeline. Verification is dropped; changedFiles/tokenBreakdown empty; retriesUsed 0/maxRetries 3 fabricated. Several preserved fields have no renderer. |
| getPipeline:246 | REAL derived | GET `/jobs`, then `/jobs/{id}` for first RUNNING job, else first job | QueueRoute pipeline. Overview JobPipelineGraph does **not** use this method. Failures swallowed as empty pipeline. |
| getTelemetry:263 | REAL derived counts; HARDCODED token/spend/budget | GET `/jobs`; no capacity endpoint | Called by useTelemetry inside ProviderQuotaList/QueueProjectionBar, but returned telemetry object is not rendered there. TopMetricsBar never consumes it. Counts default to zero on failure; failed24h has no time filter. |
| getTraceEvents:293 | REAL | GET `/events?limit=…&after=…` | Layout initial history; Overview live trace; Events route; job trace/task badges; execution timeline. Drops runId/actorId. |
| subscribeEvents:326 | REAL | GET `/events/stream?after=…` via EventSource | Layout updates global event/agent/job/message/execution stores. Drops runId/actorId. Named trace events match live stream. |
| getExecutionSnapshot:397 | REAL | GET `/execution` | Layout loader, Execution route/cards/backends, Settings backend strip, Sidebar backend/execution badges, job task badges. Keeps takenAt, details, IDs, state and expiry. |
| getProviderQuotas:441 | HARDCODED | **No endpoint called** | ProviderQuotaList on Overview and Usage: Google 56%, 666 requests left, 1,500/day, EXACT, daily reset, “AI Studio reported quota.” False measurements. MOCK has separate quota fixtures. |
| getProjections:461 | HARDCODED empty; MOCK populated | **No endpoint called** | QueueProjectionBar rows empty in HTTP mode, while static remaining/projection numbers remain visible. |
| getSettings:465 | HARDCODED | Client base URL / claimed SSE and policy text | Settings runtime/policy. Client URL and implemented SSE are configuration facts; governed execution/strict human-review policy are not read from server. Rendering preferences are local UI state. |
| sendOperatorCommand:478 | HARDCODED unsupported; MOCK simulated success | **No endpoint called** | MessageDispatcher on Agents list/detail. Returns success false; UI still clears prompt and says control-plane active. Not equivalent to real thread messaging. |
| triggerJobAction:485 | DEAD | Implements POST `/jobs/{id}/cancel`; retry/pause/promote return false | No production UI call found (only test/contract/adapter declarations). Cancel endpoint exists but was not invoked. No backend retry/pause/promote route; recovery resume is a different action. |
| getThreads:505 | REAL | GET `/threads?jobId=…&participant=…&limit=…` | OperationalThreadView inside JobDetailView. Threads are already wired, not globally missing. No standalone thread browser. |
| getThread:531 | DEAD, real implementation | GET `/threads/{id}` | useThread exists but no component uses it. List metadata currently suffices for job thread view. Verified endpoint nonetheless. |
| getMessages:553 | REAL | GET `/threads/{id}/messages?limit=…&after=…&conversationId=…` | OperationalThreadView. Hook passes only thread ID: default 50 messages, no pagination; conversation filter is client-side over fetched subset. |
| getAgentInbox:604 | DEAD, real implementation | GET `/agents/{id}/inbox?state=…&limit=…&conversationId=…` | useAgentInbox exists but no component uses it. Missing mailbox UI; jobId/threadId/chronological API filters not exposed by adapter. |
| sendMessage:625 | REAL endpoint implementation, untested mutation | POST `/messages` | OperationalThreadView composer. Source inspection confirms route/payload; only GET responses verified. UI reply selection is not passed to sendMessage. |

## Routes, features, and shared components

This inventory covers every data-bearing module in `src/routes`, `src/features`, and `src/components`. Pure geometry/theme controls are listed explicitly so they are not mistaken for absent telemetry endpoints.

| Component(s) | Status in HTTP mode | Feed / affected UI |
|---|---|---|
| routes/index.tsx (Overview) | REAL + HARDCODED | `/agents`, `/jobs`, `/events` + stream for lanes/queue/trace; embeds static metrics, active execution and budget widgets. No running job exists in the live sample, yet banner says RUNNING. |
| routes/queue.tsx | REAL + HARDCODED explanatory claim | `/jobs`, selected `/jobs/{id}`, `/agents`; footer claims historical-median estimates and serial policy although no estimator is wired (`:114`). |
| routes/agents/index.tsx | REAL identity; HARDCODED usage/unsupported dispatch | `/agents` → AgentLaneCard and MessageDispatcher. |
| routes/agents/$agentId.tsx | REAL identity/status; HARDCODED detail | `/agents` lookup; detailed panels below; fake `trc <id>·active` fallback at :60. No real inbox or runs retrieval. |
| routes/usage.tsx | HARDCODED metrics + REAL agent labels | `/agents` labels; fallback context 25%/0k/200k/“active”; static budget/projections and adapter quota. HTTP-mode demo banner at :17 does not make these measured values. |
| routes/events.tsx | REAL feed; incorrect classification | `/events` + stream, `/agents` labels. Errors filter uses mock-era kinds, missing live job.failed and execution failures. |
| routes/execution.tsx | REAL | `/execution` + execution events; groups resources, availability, expiry and timeline. Has error/loading/refresh states. |
| routes/settings.tsx | REAL + HARDCODED/local | `/agents` and `/execution` for operators/backends; getSettings static policy/runtime; local rendering preferences. |
| components/Layout.tsx | REAL infrastructure | Starts event history/stream and execution snapshot loader; mounts Header, Sidebar and modals. |
| components/Header.tsx | REAL + honest placeholders | `/health` store + `/agents`; HTTP budget/queue ETA are `—`, unlike Overview's fake equivalents. Health is loaded at stream initialization, not periodically by the unused useHealth hook. |
| components/Sidebar.tsx | REAL + HARDCODED | `/execution` derived active count/backend state; Queue “4”, Agents “3”, Events “live” fixed at :16–19; store clock starts at demo time. “Herdr Online” means executable on PATH, not a running sandbox. |
| components/JobModal.tsx | REAL wrapper | Selected ID → `/jobs/{id}` via JobDetailView. Overview supplies fabricated #142, so live modal opens missing job. |
| components/DossierModal.tsx | REAL presentation + local assets | Selected `/agents` presentation/characterCardUrl, synthesized card fallback; no runtime dossier endpoint. |
| AgentLaneCard | REAL labels/status; HARDCODED telemetry | `/agents`; fallbacks 30%, 50k/200k at :22–24, queue 0/session 0k at :188–192. |
| AgentPortrait | REAL presentation + local visual fallbacks | `/agents` presentation/status/phase; geometric fallback and animations are decorative, not telemetry. |
| AgentContextMeter | HARDCODED detail/placeholders | getAgent placeholders; displays 0k/200k and zero percentage segments despite unavailable measurements (:15–18). |
| AgentActivityList | HARDCODED empty; MOCK populated | getAgent activity []; derive real activity from events/currentTask/activeTool, not empty mock detail. |
| AgentMetricsGrid | REAL STATUS only; MOCK extra metrics | getAgent constructs STATUS from `/agents`; other mock metrics not available. |
| AgentRunsTable | HARDCODED empty; MOCK populated | getAgent runs []; says no recent runs even though no runs endpoint was queried. Wire `/jobs/{id}/runs`, filtered by actor. |
| AgentAllowanceCard | HARDCODED honest unavailable; MOCK populated | N/A quota/capacity/reset detail. Wire provider usage with appropriate unknown state. |
| TopMetricsBar | HARDCODED | Running 2, queued 4, blocked 1, failed 0, spend $4.12, budget 58%; tokens store `—` in HTTP. No telemetry hook. |
| TokenBudgetMeter | HARDCODED | 173k/300k, 246k completion/hard-stop, 54k spare, redis-state/6 jobs; no endpoint. |
| BudgetRiskAlert | HARDCODED | Invented #148/~9k overrun; raise-cap button only alerts success (:26), changes no policy. |
| ProviderQuotaList | HARDCODED | getProviderQuotas static row in both compact/full layouts. No live capacity call. |
| QueueProjectionBar | HARDCODED + MOCK rows | getProjections [] in HTTP; still shows 91k remaining/~12k remainder and a budget warning (:15,35,47,83). |
| ActiveExecutionCard | HARDCODED | Static #142 Redis job, RUNNING, repository/branch/start time, 80k cap, ETAs/34-run confidence; store elapsed is fabricated. |
| JobPipelineGraph | HARDCODED default; REAL-capable props | ActiveExecutionCard supplies no steps; default BUILD/HARDEN/VERIFY/COMPLETE actors/states/notes at :15, including auto-merge claim. `/agents` only supplies presentation. |
| QueueTable | REAL jobs/labels; unavailable estimates | `/jobs` and `/agents`; estimates `—`, no hidden estimation service. Filters omit running/failed tabs but All includes them. |
| JobDetailView | REAL core + missing detail + false policy/elapsed | `/jobs/{id}`, `/threads`, `/messages`, `/agents`, global event buffer; renders phases/artifacts/thread/events. Does not render tasks/observations/errors/retry/verification/progress. |
| OperationalThreadView | REAL messages/artifacts; unwired reply | `/threads?jobId`, `/threads/{id}/messages`, `/agents`; composer endpoint source-reviewed. Always says live substrate, suppresses fetch errors and can show false empty state. |
| AgentChatterFeed | DEAD | Unimported feature; would use event buffer with outdated mock-era event-kind filter. Remove or update before enabling. |
| MessageDispatcher | HARDCODED unsupported; MOCK success | getAgents for options, sendOperatorCommand stub for dispatch; currently no real command integration. |
| ToolCallItem | DEAD | No production import; Events route renders tool events generically. Wire to tool.* events or remove unused component. |
| ExecutionBackendStrip | REAL | `/execution` backend rows/OpenRig ledger; shared by Settings and Execution. |
| ExecutionResourceCard | REAL | Snapshot + event reducer resource fields, task/job/execution IDs, reused/generation/expiry/failure. Live resources were empty at audit. |
| ExecutionTimeline | REAL | execution.* subset of global event buffer; latest 50 rows, not complete durable history. |
| JobTaskExecution | REAL but history-limited | Job-filtered execution events + live resources; guards reuse by executionId. Does not load job-scoped durable history. |
| executionFormat.ts, useNow.ts | REAL-derived/local clock | Formatting/grouping/expiry and Date.now countdown; no endpoint needed. |
| Badge, CyberButton, AnimatedCube, AmbientGyro | HARDCODED/local presentation | Labels/props/theme/animation; no independent runtime data claim or missing endpoint. |

## Field and semantic discrepancies

References below are LysControl paths unless prefixed `Hermes:`. “Dropped” means absent from adapter output; “unrendered” means preserved but not shown. Normalization/fallbacks are documented even when legitimate.

### Agents and health

1. `src/api/adapters/httpAdapter.ts:92`: `/agents` is an identity/status registry, not per-agent telemetry. ContextPct/contextUsed/contextMax/queueDepth/sessionTokens are absent live and never mapped. AgentDetail activity/runs/allowance/tokens are invented placeholders at :125–144. Do not interpret missing data as 0%, 0k or a 200k limit.
2. `src/api/adapters/httpAdapter.ts:100`: status uppercased with `as any`, without validating AgentStatus. Live IDLE fits; unknown future status is not checked. Empty/missing identity values become generic provider/model/role and synthetic capability `execution` (:96–99), which should be identified as fallbacks, not registered facts.
3. `src/api/adapters/httpAdapter.ts:103` and `src/api/types.ts:139`: currentTask/activeTool are optional strings but actual JSON contains null and mapping retains it. PersonaProfile.systemPromptFragment is optional string at types.ts:72 but live null is retained in the whole persona object.
4. `src/api/adapters/httpAdapter.ts:104`: presentation mapping selectively retains displayName/accent/avatar/card/sigil/code/subtitle/persona. Declared `AgentPresentation.animationProfile` and `badge` (types.ts:91,94) are not mapped if supplied; not present in current live response. Live null characterCardUrl is replaced by an inferred local URL (:108), so null no longer means no dossier. Actual null accent values are generally replaced by UI colors; this is presentation enrichment, not server color truth.
5. `/health` fields match types.ts:41; version and uptime are real service metadata. Connection badge is not a measurement of agent/provider availability. `useAgents` also sets CONNECTED on a successful fetch (hooks.ts:69), which can overwrite SSE-disconnected state.

### Jobs, phases, pipeline and overview telemetry

6. `src/api/adapters/httpAdapter.ts:162`: getJobs drops live blockedReason/repairCount/replanCount present in the summary response. Those fields are declared in Job (types.ts:260–262). Preserve them for queue diagnostics.
7. `src/api/adapters/httpAdapter.ts:176`: estimatedTokens/estimatedTime/budget become `—`, and policy becomes literal `governed · serial`. API summary has no such policy field. `getJob` lacks policy, but JobDetailView.tsx:85 independently uses the same literal fallback. Reactive execution can run concurrent tasks; this text is not reliable evidence of serial execution policy.
8. `src/api/adapters/httpAdapter.ts:225`: job/phase fields are passed through without nullable DTO types. Job.startedAt/completedAt/progress/currentPhase and JobPhase.agentId/durationMs/startedAt/completedAt/commitSha/changedFilesCount/detail can be null in backend schemas (Hermes jobs/job_service.py:20–65), whereas corresponding frontend fields generally allow only undefined (types.ts:223,241). Live phase durationMs/startedAt/detail are null. Message and thread optional IDs also need null treatment below.
9. `src/api/types.ts:223`: JobPhase omits live dependencies and requiredCapabilities. Raw phases are preserved by getJob, so these are untyped, not actually removed. Pipeline mapping (:192–212) discards order, dependencies, requiredCapabilities, attempts, timestamps, durationMs, changedFilesCount and detail; it also renames name → phase/task, status → a coarse state, role → note, and commitSha → truncated meta. Clearly label this as a projection, not the actual dependency graph.
10. `src/api/adapters/httpAdapter.ts:194`: SUCCEEDED→COMPLETED, FAILED/CANCELLED/BLOCKED→BLOCKED, SUPERSEDED→IDLE, all other states default QUEUED. SKIPPED therefore appears queued, not terminal skipped. Cancellation and failure lose their distinctions. JobDetailView's direct phase renderer (:99) also styles only SUCCEEDED/RUNNING/FAILED specially.
11. `src/api/adapters/httpAdapter.ts:216`: live `verification` is dropped completely and there is no corresponding JobDetail.verification type. `testSummary` (types.ts:296) is a different shape and is never populated. Backend verification contains status/results (Hermes jobs/job_service.py:262), not necessarily test totals; map honestly without inventing passed counts.
12. `src/api/adapters/httpAdapter.ts:236`: changedFiles [], tokenBreakdown [], retriesUsed 0, maxRetries 3 are static. Backend only exposes phase changedFilesCount/commitSha and retryHistory, not these synthesized detail facts. Actual file paths cannot be inferred from counts; retriesUsed can be derived from valid attempts/history, but maxRetries requires policy evidence.
13. `src/features/jobs/JobDetailView.tsx:99`: tasks, observations, blockedReason, repairCount, replanCount, errors and retryHistory are kept by getJob but not rendered. Live FAILED_TESTS error explains the failed job; current detail UI does not show that error list. Progress 0.5 also remains unrendered.
14. `src/api/adapters/httpAdapter.ts:249`: pipeline falls back to jobs[0] when nothing is RUNNING. The live sample has only a FAILED job; Queue's pipeline therefore describes a historical failed job, not active work. Make selection and terminal status explicit. `catch` (:258) converts failure into apparent empty pipeline.
15. `src/api/adapters/httpAdapter.ts:269`: failed24hCount counts all FAILED entries returned, without completedAt filtering. All counts cover only default latest 50 jobs, not necessarily the fleet. PLANNING/VERIFYING/REPAIRING are not counted as active. On API error :280 returns zeros, hiding failure as zero work. `useTelemetry` loads once (hooks.ts:232), unlike useJobs' event-version refresh.
16. `src/api/adapters/httpAdapter.ts:276`: token/spend placeholders and budget 0 are not capacity telemetry. OverviewTelemetry shape does not match `/capacity/telemetry`; no DTO or mapping exists. Capacity aggregate tokens are registry/process totals, not daily-window tokens. There is no exposed cost or sprint-budget denominator, so don't simply rename totals to “today” or compute a percentage against a fictitious cap.
17. `src/stores/useConsoleStore.ts:177`: elapsed is 521 + client ticks in **both** modes, unrelated to selected job.startedAt/completedAt. JobDetailView.tsx:84 displays it for real running jobs. Header/Sidebar clock also uses demo baseTs, not wall clock. Derive real elapsed from timestamps and freeze terminal durations.

### Events and execution

18. `src/api/adapters/httpAdapter.ts:45` (DTO), :306 (history), :350 (SSE), and `src/api/types.ts:332`: backend `runId`/`actorId` are missing from types and dropped in both event mappings. Live execution release had actorId claude; that attribution is lost despite intact taskId/metadata. Add optional nullable IDs and preserve them.
19. `src/api/types.ts:49,332`: API ActorRef.accentColor is nullable; optional string does not represent null. Event jobId/taskId are likewise nullable in live JSON; mappings retain null. rawTs is correctly seconds and must not be reinterpreted as milliseconds; D-009 takenAt is correctly preserved (:433). dur is display text; do not assume numeric duration from it.
20. `src/routes/events.tsx:27`: Errors filter only recognizes error/retry/quota.warn; live job.failed, agent.failed, execution.failed and execution.release_failed are excluded. Coloring at :12 and Overview index.tsx:23 has the same obsolete vocabulary. agent/phase/job reducers partly use modern names, so feed classification should use the actual runtime taxonomy.
21. `src/features/jobs/JobDetailView.tsx:52`: job traces use only the global 100-event initialization (hooks.ts:293) and 150-row store cap (useConsoleStore.ts:125). Durable `/jobs/{id}/events` is never fetched. “No trace events recorded” is not justified for an older job outside that buffer. Matching job.sprintId can also mix attempts sharing a sprint identifier; prefer unique job ID and explicit legacy handling.
22. `src/api/adapters/httpAdapter.ts:405`: execution snapshot renames nothing meaningful; maps booleans/default details/null IDs and preserves cutoff. Snapshot resource.details (including restored flag/age-related diagnostics) survives. Backend restoredAt is not typed/mapped as a top-level ExecutionResource field; this is a schema extension, not part of original D-009. Live empty resources prevents empirical testing of each populated field.
23. `src/components/Sidebar.tsx:36`: herdr.available from `/execution` means executable exists, not a live Herdr session; “Online/Offline” overstates that probe. Use “Available/Unavailable.” Execution count intentionally counts acquiring/running, excluding ready/idle; define this clearly rather than treating it as all held resources.

### Messaging

24. `src/api/types.ts:187,205`: Message intent/conversationId/replyTo/correlationId/jobId/phaseId and Thread.jobId/title are optional strings but can be null; live replies/correlation IDs are null. `getMessages` retains these values. Actor colors are replaced with presentation fallbacks; actor avatar/subtitle are enriched from local resolver when absent. Identity/text/kind/timestamps/artifact trust and metadata are otherwise preserved.
25. `src/api/adapters/httpAdapter.ts:519,542`: thread participant mapping retains only id/kind/displayName/accentColor, dropping optional avatarUrl/subtitle if supplied (not in live sample). Inbox mapping (:616) keeps raw embedded message without the getMessages presentation enrichment; normalize consistently if its UI is wired.
26. `src/features/messaging/OperationalThreadView.tsx:53`: reply UI stores replyToMessageId, but sendMessage receives only five arguments. Selected replyTo/conversationId/correlationId are not sent even though the adapter supports them. The server will receive an ordinary operator_note rather than an attributed reply. Source-only finding; no message was sent to prove it.
27. `src/api/adapters/httpAdapter.ts:554`: default messages limit 50; hook has no paging/cursor/conversation arguments. Server returns chronological subset; client conversation filtering sees only that subset, not all thread conversations. Thread selector currently uses one matching/first thread (:20), leaving other job threads inaccessible. HTTP 404 maps to [] (:561), and view ignores hook errors, conflating missing/unavailable with no messages.
28. `src/api/adapters/httpAdapter.ts:604`: GET inbox supports jobId/threadId/chronological on backend (Hermes main.py:616); adapter omits them. There is no mailbox renderer, so pending/acknowledged operational delivery is invisible. Mailbox acknowledgedAt explicitly permits null and matches live ACKNOWLEDGED envelope.
29. `src/api/adapters/httpAdapter.ts:657`: sendMessage response actor mapping omits avatarUrl/subtitle that getMessages retains. Current composer discards the returned object and refetches, so this discrepancy is not presently visible; unify shared mapping rather than duplicating it.
30. `Hermes main.py:406` and `runtime/storage/schema_registry.py:66`: `/jobs/{id}/events` has two response shapes. The live sample used the bus fallback (source/rawTs/dur), but persisted events use StoredRuntimeEvent.to_dict: event_id/id, job_id/jobId, sequence, event_type/eventType/kind, occurred_at/ts, schema_version, snake/camel task/run/actor IDs, parent_event_id/causation_id/correlation_id, payload/detail/metadata. This persisted envelope lacks source/rawTs/dur. Before wiring job history, normalize it explicitly (rawTs from occurred_at, actor/source from known context, dur unknown), preserve sequence/causality and do not reuse the current `/events` DTO unchecked. These populated durable responses were not available in the live sample.

## Gaps in both directions and implementation recommendations

| Available Hermes surface / unsupported UI | Recommendation |
|---|---|
| GET `/capacity/telemetry` (main.py:518) | Add typed snake_case DTO for timestamp/summary/providers/jobs_tracked. Wire Usage and Overview provider measurements; show “not reported” when providers empty. Provider records contain provider_id/status/status_reason/total_requests/success_count/failure_count/success_rate/throttling_count/failure_breakdown/usage. Usage can contain context/request/token/reset/source data (runtime/capacity.py:641); populated provider records are code-verified only. Preserve source/confidence; do not claim EXACT for estimates. |
| GET `/jobs/{id}/telemetry` (:526) | Wire job total/input/output/cached tokens. Map job_id → jobId explicitly. No cost, per-actor attribution or cap exposed; show unavailable rather than fabricate tokenBreakdown/spend/budget. All-zero telemetry for the sampled runner means no tracked usage, not proof it spent zero tokens. |
| GET `/jobs/{id}/tasks`, `/runs`, `/observations` (:352,366,380) | Add typed task graph/run/observation DTOs, show diagnostics in JobDetailView, derive AgentRunsTable by actor across known jobs. Do not assume empty arrays in current runner sample establish all possible schemas. |
| GET `/jobs/{id}/events` (:394) | Fetch job history when opening modal, normalize canonical stored envelopes separately from the live bus envelope, merge/dedupe with SSE, request up to backend limit 500 and state retention limits. No cursor is exposed here; do not promise full paging without backend support. Use for JobTaskExecution as well as trace. |
| GET `/jobs/recoverable` (:455) | Fix backend route ordering before frontend wiring; add recovery queue/view with honest loading/error state. Current literal route is unreachable live. |
| GET `/jobs/{id}/recovery` (:495) | Recovery diagnostics panel, showing recoveryCount/events; 404 means no canonical recovery record, not nonexistent visible job. |
| GET `/threads`, `/threads/{id}`, `/threads/{id}/messages` | Already partially wired in job modal. Add standalone thread selector/browser and paging; use getThread only where extra metadata is needed. No need to implement duplicate thread APIs. |
| GET `/agents/{id}/inbox` (:616) | Add Pending/Delivered/Acknowledged mailbox to agent detail with job/thread/conversation filters and chronological option. Ack is a distinct POST requiring an explicit user action; not exercised here. |
| POST `/messages` (:590), `/jobs/{id}/cancel` (:441), `/jobs` (:420), `/jobs/{id}/resume` (:470) | Existing backend capabilities are partly missing from UI. Thread send is wired; cancel method has no UI; create/resume have no adapter method. Add explicit action controls and response/error handling only in implementation work, not during this audit. Generic operator command, retry/pause/promote, raise-cap policy changes have no equivalent endpoint; disable/remove or distinguish recovery from retry. |
| GET `/ready`, `/version`, `/info`, `/metrics` (:285–304) | Optional Settings/service diagnostics. `/health` already supplies version/uptime, so avoid redundant requests; metrics can provide request count. Environment text in `/info` is server-provided but itself static development metadata. |
| Context/queue-depth/session widgets | Use provider usage.context_used/context_window only when available and attributable to that actor; derive queued tasks from actual task assignments with explicit semantics. Otherwise show unknown. Provider aggregate tokens are not actor-session context occupancy. |
| Budget/ETA/projection/spend/risk widgets | No exposed sprint cap, costing catalog, estimator or hard-stop policy endpoint. Remove invented values/actions or show unavailable. Historical durations/usage may support an explicitly labeled estimator later; they do not justify the current static confidence claims. |
| Changed file list, test totals, retry limit | Phase count/commit data alone cannot supply paths/test totals/maxRetries. Display counts/refs and verification results as available; leave unsupported richer panels empty. |
| Local theme/preferences/portraits | Keep local; no backend endpoint needed. Distinguish decorative asset metadata and local rendering settings from runtime policy enforcement. |

## Prioritized implementer checklist

Priorities here follow the requested audit definition: **P1 false data**, **P2 missing real data**, **P3 polish**. They are not production incident severities.

### P1 — stop presenting false runtime facts

- [ ] Replace Overview static TopMetricsBar counts/spend/58% (`features/telemetry/TopMetricsBar.tsx:14`) with truthful derived counts and unknown spend/budget. Current live counts: zero RUNNING/QUEUED/BLOCKED and one FAILED job, unlike the displayed 2/4/1/0.
- [ ] Wire ActiveExecutionCard to a selected real active job and getPipeline; show “No active execution” for the observed sample. Remove #142 Redis job/ETAs/34-run confidence (`features/jobs/ActiveExecutionCard.tsx:24`, `routes/index.tsx:46`, `features/jobs/JobPipelineGraph.tsx:15`). Modal target must be its actual job ID.
- [ ] Remove HTTP-mode fabricated Google EXACT quota (`api/adapters/httpAdapter.ts:441`); wire provider telemetry with unknown/estimated states. Remove fabricated TokenBudgetMeter (`features/telemetry/TokenBudgetMeter.tsx:14`), BudgetRiskAlert and fake raise-cap success (`features/telemetry/BudgetRiskAlert.tsx:26`), and 91k/~12k projection totals (`features/jobs/QueueProjectionBar.tsx:15`).
- [ ] Replace context/session/queue fallbacks with unknown (`features/agents/AgentLaneCard.tsx:22`, `AgentContextMeter.tsx:15`, `routes/usage.tsx:36`) and fake active trace ID (`routes/agents/$agentId.tsx:60`). Unknown must not appear as measured zero.
- [ ] Derive job elapsed from timestamps (`stores/useConsoleStore.ts:177`, `features/jobs/JobDetailView.tsx:84`); replace Sidebar static queue/agent badge counts (`components/Sidebar.tsx:16`) and mock clock with real/local facts.
- [ ] Fix failed24h filtering/window and error-to-zero behavior (`api/adapters/httpAdapter.ts:269,280`); remove unverified serial/strict-policy statements (`:179,471`, `routes/queue.tsx:114`).
- [ ] Make Events Errors include the actual failure taxonomy (`routes/events.tsx:27`); keep CANCELLED/FAILED/SKIPPED distinctions in pipeline (`api/adapters/httpAdapter.ts:194`).
- [ ] Disable or honestly label generic dispatcher instead of active control-plane claims (`features/messaging/MessageDispatcher.tsx:35`), and preserve prompt when success is false (:21). Message dispatch is distinct from executing arbitrary operator commands.
- [ ] Label Herdr as available-on-PATH, not online (`components/Sidebar.tsx:36`); expose fetch errors instead of “no messages/runs/traces” when data was never queried or failed.

### P2 — expose and preserve real data

- [ ] Add capacity/job telemetry DTOs and adapters; wire provider usage and job token breakdown supported by those schemas. Never convert process totals to daily totals without timestamps/window aggregation.
- [ ] Preserve event runId/actorId in history and SSE (`api/adapters/httpAdapter.ts:306,350`, `api/types.ts:332`); add nullable DTO fields for actual nulls and shared mapping functions.
- [ ] Preserve getJobs summary diagnostics, type phase dependencies/capabilities, expose task/observation/error/verification/repair/replan/progress/retry information in job detail (`api/adapters/httpAdapter.ts:162,216`, `features/jobs/JobDetailView.tsx:99`). Render current live FAILED_TESTS explanation.
- [ ] Fetch `/jobs/{id}/events`, `/runs`, `/tasks`, `/observations`; normalize persisted event envelopes, merge history and SSE by IDs with retention indicators. Add backend cursor support if full job-event paging is needed. Do not infer nonexistent history from the global latest-event cap.
- [ ] Fix Hermes static `/jobs/recoverable` route shadowing (`Hermes main.py:338,455`), then add recoverable jobs/recovery diagnostics and separately reviewed create/cancel/resume actions.
- [ ] Add agent mailbox, thread selection/pagination, expose inbox filters; send the selected reply IDs/context (`features/messaging/OperationalThreadView.tsx:53`).
- [ ] Refresh telemetry/agent identity after reconnect and on relevant events; hooks currently load identity once and telemetry once, while SSE overlays only agent status/currentTask (`api/hooks.ts:84,232`). Keep connection health, stream status, and provider health distinct.

### P3 — consistency and polish

- [ ] Unify nullable actor/message/presentation mapping, explicitly label local asset fallbacks, preserve animation/badge fields if supported.
- [ ] Use consistent timezone formatting (job detail slices ISO strings at `JobDetailView.tsx:82`, message view uses local Date); display epoch seconds correctly.
- [ ] Remove or wire unused getThread/getAgentInbox hooks and AgentChatterFeed/ToolCallItem; update chatter vocabulary if enabled. Remove unused fabricated retriesUsed/maxRetries detail fields unless backed by policy.
- [ ] Add clear unknown/loading/error/empty states, window labels, freshness timestamps, and pagination controls rather than broad demo banners around mixed real and false data.
- [ ] Add contract tests using observed JSON/nulls, missing provider telemetry, terminal jobs, nonempty run/task schemas, modern failure events, reply context, and history beyond the global buffer. Assert no HTTP-mode widget displays unbacked metrics or success claims. Mutations need isolated test fixtures, not live audit requests.

## Verification limits

The running service had one historical failed sprint, three idle agents, no current execution resources, and no capacity provider measurements. Empty collections were verified as empty, not populated record contracts. Populated schema conclusions are explicitly based on source/types, and all mutation capabilities are source-only. A reported GET can perform server-side read-only backend probing (notably `/execution`); this audit did not invoke the rig CLI itself. No claim is made that the API's own upstream accounting, job reducer, or telemetry completeness has been independently validated.
