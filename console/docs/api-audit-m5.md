# M5 API truth verification

**Verdict: BLOCK** — `feat/usable-console`, HEAD `d65ac04`.

Reviewed against the original `docs/api-audit.md` P1/P2 checklist and `docs/console-spec.md` M1–M4. Live curl GET checks ran on 2026-10-14 around 08:47 UTC against `http://localhost:8000`. No POST/PUT/DELETE, `/internal/*` calls or rig commands were made. Only this report was written. Original checklist priorities mean P1 = false data, P2 = missing real data, P3 = polish; that convention is used here.

`npm run test -- --run`: **22 test files passed, 175 tests passed**. Passing tests do not cover all populated-data and request-race cases below. No browser mutation or live agent execution was attempted.

## Live evidence and limits

| GET | Result |
|---|---|
| `/health` | 200; real version, uptime and timestamp. |
| `/agents` | 200; gemini/claude/codex IDLE; real identity/persona/presentation, nullable currentTask/activeTool/card URL. No context or session counters. |
| `/jobs`, `/jobs/recoverable`, `/threads` | 200; all empty. The previous recoverable route defect is fixed in the running API. |
| `/capacity/telemetry` | 200; providers `{}`, jobs_tracked 0, actual summary totals all 0. No provider usage sample. |
| `/execution` | 200; subprocess/herdr/openrig available; resources empty; daemon up; ledger owners 0/rigIds []; numeric takenAt. |
| `/events?limit=3` | 200; runtime.started envelope with null jobId/taskId/runId/actorId, numeric rawTs. |
| `/jobs/audit-missing-job` | 404, expected nonexistent job. |
| `/jobs/audit-missing-job/telemetry` | 200; zero input/output/cached/total tokens. Backend returns zero tracked usage even for an unknown ID; this is not evidence of no token spend. |

No unexpected live endpoint errors occurred. Job-specific populated records, message replies, resource reuse, provider quotas and concurrent request timing were assessed from mappers/renderers and the real Hermes schemas: `runtime/task_graph.py`, `runtime/execution.py`, `runtime/observations.py`, `runtime/capacity.py`, `runtime/storage/schema_registry.py`, `jobs/job_service.py`, and `main.py`. Empty live collections do not validate those populated cases. SSE mapping was inspected; the earlier audit verified the live stream envelope, while this pass's GET history confirmed the same bus IDs/null conventions.

## Every original P1 checklist item

Each row corresponds to one original checklist bullet. PARTIAL means at least one subrequirement remains, even where the main fabrication was removed. WONTFIX(backend) is used only for explicitly excluded backend capability work, not for frontend omissions.

| Original item | Status | Evidence / remaining work |
|---|---|---|
| Replace static TopMetricsBar counts, spend and 58% | **RESOLVED** | `src/features/telemetry/TopMetricsBar.tsx:24` uses real job counts/capacity totals; `:69` labels tokens since runtime start; spend/budget unknown. `/jobs` sampleSize is disclosed. No fake 2/4/1/0 or bill remains. |
| Wire active card/pipeline/modal ID; remove #142/ETAs/confidence | **PARTIAL** | `features/jobs/ActiveExecutionCard.tsx:17` selects an actual active job, `:33` honest no-active state, `:63` uses actual ID, `:87` real detail graph. However old detail responses can populate a newly selected job's pipeline; finding F1. |
| Remove fake EXACT quota, run budget, risk/raise-cap and projection totals | **RESOLVED** | `features/telemetry/ProviderTelemetryList.tsx:80` loads capacity; `features/telemetry/TokenBudgetMeter.tsx:1` and `features/jobs/QueueProjectionBar.tsx:1` show unavailable instead of fabricated limits/projections. BudgetRiskAlert is removed. No cap-change success claim remains. |
| Context/session/queue unknown; remove fake active trace ID | **RESOLVED** | `api/adapters/httpAdapter.ts:210` detail percentages/tokens unknown; `features/agents/AgentContextMeter.tsx:1`, `AgentLaneCard.tsx:22`, `routes/usage.tsx:87` show unknown, no 30%/50k/200k/active trace fabrication. New dossier exposes activeTool/currentTask only when supplied. |
| Real elapsed/clock and Sidebar counts | **RESOLVED** | `features/jobs/jobTiming.ts:1`, `JobDetailView.tsx:94` and `ActiveExecutionCard.tsx:80` derive from timestamps. `components/Sidebar.tsx:42` derives badges; clock is wall time, not the old demo epoch. |
| Correct failed24h, error-to-zero, serial/strict policy claims | **RESOLVED** | `api/adapters/httpAdapter.ts:329` applies 24h completion-time filter, returns null when timestamp missing, propagates request failure; `:473` policy not exposed. No serial/human-review policy is asserted as server state. |
| Real failure taxonomy and separate phase outcomes | **RESOLVED** | `features/events/eventKinds.ts:1`, `routes/events.tsx:15`, `api/adapters/httpAdapter.ts:71` preserve FAILED/CANCELLED/SKIPPED and filter modern failure events. |
| Honest generic dispatcher; keep input on failure | **RESOLVED** | `features/messaging/MessageDispatcher.tsx:1` is unavailable rather than a false successful command. Dossier dispatch disabled at `features/agents/AgentDossier.tsx:45`. Actual thread send keeps text on errors (`OperationalThreadView.tsx:68`). Reply attribution remains a separate P2 gap (F3). |
| Herdr availability, fetch errors versus false emptiness | **PARTIAL** | `components/Sidebar.tsx:59` uses Available; most views use shared errors. `features/jobs/JobRealData.tsx:43` hides refresh error whenever stale tokens exist, and agent/job inspectors suppress errors when prior detail exists. Stale data can look current; F1/F2. |

## Every original P2 checklist item

| Original item | Status | Evidence / remaining work |
|---|---|---|
| Capacity/job DTOs; real usage without daily-total mislabeling | **PARTIAL** | `api/mapping.ts:159,189`, `api/adapters/httpAdapter.ts:652,656`, `features/telemetry/UsageMeters.tsx:1`, `JobRealData.tsx:41` wired. Source/window labels and reported zeros handled reasonably. Missing values still become numeric zero in job/provider mappers; see unknown inventory. Per-provider failures/reset/context data are partly mapped but not all rendered. |
| Keep event runId/actorId; nullable IDs/shared mapping | **PARTIAL** | `api/mapping.ts:61,83` preserves nullable IDs on bus and stored paths; `routes/events.tsx:118` displays them. Job detail trace still omits both (`JobDetailView.tsx:224`), and stored envelope causality/sequence is dropped. Agent DTO null typing/presentation mapping remains loose. |
| Summary diagnostics, phase dependencies, job verification/repair/replan/progress/retry/errors | **PARTIAL** | `api/adapters/httpAdapter.ts:44,299` keeps summary/detail diagnostics and verification. MissionBoard renders progress/blocked reason (`:131,147`), JobFailure shows actual errors (`JobRealData.tsx:25`). Verification results, repair/replan counts and retry history still have no renderer; F4. Phase dependencies/capabilities are retained raw but absent from graph presentation. |
| Job events/runs/tasks/observations, normalization/dedup/retention | **PARTIAL** | `api/adapters/httpAdapter.ts:661–687`, `api/mapping.ts:83,201,223,240`, `features/jobs/JobRealData.tsx:67,97,122` wired. `jobEvents.ts:14` dedupes and sorts. No retention/page indication for 500 requested/50 displayed. Bus fallback incorrectly labeled durable, F5. Agent recent runs still explicitly not wired (`AgentRunsTable.tsx:52`). |
| Recoverable route, recovery diagnostics and create/cancel/resume | **PARTIAL** | Discovery is now wired (`api/adapters/httpAdapter.ts:246`, `api/hooks.ts:364`, Queue's recoverable area). Live discovery 200. `/jobs/{id}/recovery` diagnostics still unwired (**OPEN**, frontend). Mutations intentionally excluded in console-spec: **WONTFIX(backend/scope)** here; no fake controls added. The route shadowing itself is resolved upstream, not still open. |
| Agent mailbox/thread selector/paging/inbox filters and reply context | **OPEN** | `api/hooks.ts:585` inbox hook still has no rendered consumer. `OperationalThreadView.tsx:22` selects one matching/first thread; no thread paging/selector; `useMessages` fetches default first 50. Reply state remains unsent (F3). Required inbox jobId/threadId/chronological adapter filters remain absent. |
| Refresh identity/telemetry on reconnect/events; distinct connection health | **PARTIAL** | `api/hooks.ts:87,258,307,444` refreshes roster/telemetry and marks runtime resynced; `stores/useConsoleStore.ts:181` bumps versions. `useAgent` depends only on id, not agentRuntimeVersion (`hooks.ts:124`), so selected dossier's model/role/capabilities/activeTool remain stale after reconnect. Reconnect resync waits for the next event; silent stream recovery alone doesn't trigger it. Successful agents GET can overwrite stream-disconnected status (`hooks.ts:71`). |

## Reachable findings requiring fixes

### F1 — P1: selected identity and job detail can show another selection's data

**`src/api/hooks.ts:114`, `src/api/hooks.ts:183`**.

Neither `useAgent` nor `useJob` cancels or fences earlier requests, clears data on identity change, or checks the response's identity against the current selection. Select agent A, then B while A's request is delayed: B can resolve first and then A overwrites baseAgent. The B route displays A's dossier; `useAgent` can also overlay B's status/currentTask on A's identity. This is reachable through normal roster navigation with delayed GETs, not dependent on fabricated API data. The same stale response problem applies when a job selection changes and when overlapping job event refreshes resolve out of order; an older RUNNING detail can overwrite a newer terminal detail. ActiveExecutionCard can show the new job's title with the previous job's graph.

`useResource` has a response-active guard (`hooks.ts:282`), but retains old data across key changes (`:283`) without an identity key. ActiveExecutionCard's mounted JobTokens can therefore render A's totals for B until B loads; an error fetching B leaves A's totals indefinitely. Fix key-scoped data/reset and request sequencing; retain stale data only for refreshes of the **same** resource. Test A/B responses resolving in both orders, resource changes that fail, and old same-job responses racing a terminal refresh.

### F2 — P2: refresh failures are hidden behind prior inspector/token data

**`src/features/jobs/JobRealData.tsx:44`**, related `features/jobs/JobDetailView.tsx:30`, `features/agents/AgentWorkspace.tsx:46`.

JobTokens renders an error/retry only when no telemetry exists. After one successful load, a subsequent failed refresh displays the old number without a stale label, error, retry or freshness. Job detail/dossier similarly show stale prior detail without a refresh-error notice. Global ConnectionBanner only covers network reachability; HTTP 500/404 is recorded as successful contact, so it does not fix this. Show StaleNotice plus last-loaded freshness when same-resource data is retained and refresh fails. Test a successful response followed by an HTTP error.

### F3 — P2: the Reply action silently sends an ordinary note

**`src/features/messaging/OperationalThreadView.tsx:58`**.

Clicking Reply sets replyToMessageId and targetRecipient and displays “Replying to…”, but sendMessage receives only targetThreadId/text/to/kind/intent. It receives no replyTo, conversationId or correlationId. The real POST payload supports all three (`api/adapters/httpAdapter.ts` sendMessage). A successful send clears the reply state, even though no reply relationship was submitted. Pass selected message IDs/context through, or remove the Reply affordance. This was in the original audit and is still open. No POST was made in this review.

### F4 — P2: verification and repair/retry diagnostics still stop before render

**`src/features/jobs/jobEvents.ts:53`**, **`src/features/jobs/JobDetailView.tsx:202`**.

The adapter keeps verification, retryHistory, repairCount/replanCount, but no general diagnostic panel renders them. explainFailure prints only verification.status and only for FAILED/BLOCKED/CANCELLED jobs; verification.results and successful-job verification evidence are inaccessible. The new tasks/runs/observations panels do not fill that gap. These are real supported `/jobs/{id}` fields (Hermes jobs/job_service.py:54–64, :262), so this is remaining frontend M2 work, not a backend excuse. Show structured or safely formatted raw verification results/attempt history and counts with honest unavailable states; do not manufacture test totals or a maxRetries policy.

### F5 — P1: bus history is falsely called durable history

**`src/features/jobs/jobEvents.ts:20`**, rendered at **`src/features/jobs/JobDetailView.tsx:241`**.

All events returned by getJobEvents are tagged stored, regardless of envelope. Hermes `/jobs/{id}/events` returns canonical stored envelopes only when store.list_events is nonempty; otherwise it returns the **in-memory event bus** fallback (Hermes main.py get_job_events). mapEvent recognizes the distinction before discarding it, but mergeJobEvents treats every first argument row as durable. For a sprint-runner job with only bus events, the UI claims “stored”/“durable history” for events that do not survive restart. This is a known supported path exercised by the original live audit. Preserve envelope provenance or label neutrally as job history. Test a bus-shaped response from the job events endpoint.

## Fresh truth/data-loss sweep

### What is now truthful

- HTTP is the default (`api/client.ts:6–18`); mock requires VITE_LYSCONTROL_MOCK=1 and Layout displays MOCK DATA. All real routes use the HTTP client rather than importing seeded data.
- No measured provider quota, financial spend, budget cap, ETA, forecast, unsupported task dispatch or cap-raising success is fabricated in current rendered widgets. Local visuals/font/theme tokens are presentation, not runtime measurements.
- Reported process summary zero is displayed as reported zero; JobTokens explicitly calls zero “tracked” and explains it is not proof of no spend. Unknown context/limit/spend remains `—` with explanation.
- Event actorId/runId are retained in both envelope mappers and displayed in global Events. Job-scoped history fetch and task/run/observation APIs are real, not mock-only.
- New graph mappings distinguish terminal statuses, while MissionBoard groups real active statuses and displays only API-supplied progress. Failure explanations use actual error content, not generic demo stories.

### Unknown still converted to zero or another invented value

| Location | Behavior | Reachability assessment |
|---|---|---|
| `api/mapping.ts:135–154` | Missing/null provider request/success/failure/throttling counts become 0; missing total requests forces unknown successRate even if a rate was provided. | Contract defect for partial telemetry; current Hermes provider serializer always supplies these counts. No observed live populated provider. **P3**, not independently blocking on an imagined response. Make count types nullable and render unknown. |
| `api/mapping.ts:193–196` | Missing/null job token fields become 0. | Mapper cannot distinguish unavailable tokens from tracked zero. Current API always emits numeric fields, including zero for an unknown job ID (live evidence above). **P3 frontend resilience; backend completeness/validation follow-up**. Do not classify observed explicit zeros as fabricated. |
| `api/adapters/httpAdapter.ts:61,299` | Missing repair/replan counts become 0; detail retriesUsed=0/maxRetries=3 remains static. | Counts are currently always emitted by backend; fabricated retry fields currently unrendered. Remove obsolete retry fields or derive legitimate history; never expose literal policy as real. |
| `api/mapping.ts:214,230` | Missing task attempt→0; missing run attempt→1. | Current task/run schemas emit attempts; fallback is an invented value for incomplete responses. Prefer null if contract expands. |
| `features/telemetry/TopMetricsBar.tsx:39` | Missing individual count becomes 0 whenever telemetry object exists. | Current getTelemetry always computes counts from successfully loaded jobs. No current API failure-to-zero bug; do not extend this convention to nullable counters. |
| `features/jobs/JobRealData.tsx:70,100,125` | Section title has collection length 0 during loading/error. | Body correctly shows loading/error. Better avoid a measured-looking zero title before load; **P3**. |

### Fields preserved in mapping but not presented

- Job detail: verification.results, repair/replan counts and retryHistory (F4). Progress is visible on MissionBoard, not job inspector; blockedReason visible there and via failure explanation. Phase dependencies/requiredCapabilities remain raw but are not shown in phase graph; task dependencies are shown instead. Phase attempt/timestamps/changedFilesCount are only partly used by phase UI.
- Task mapper retains requiredCapabilities, parentTaskId, timestamps, supersededBy and artifactRefs, but JobTasks renders description/status/attempt/actor/dependencies/error only. It drops original task metadata and supersede_reason altogether (`api/mapping.ts:201`). Task execution_backend configuration and scheduling constraints in metadata cannot be inspected.
- Run mapper (`api/mapping.ts:223`) preserves IDs/status/attempt/timestamps/exit/error/artifactRefs, but JobRuns renders IDs/status/attempt/exit/error only. It drops delegation_decision and metadata entirely. Backend_runtime_metadata and usage/context in real run metadata are consequently unavailable here. AgentDossier still doesn't load actor-filtered runs; it admits that history is not loaded.
- Observation mapper (`api/mapping.ts:240`) drops metadata. Observation renderer retains kind/actor/confidence/content but omits task/source/time/ID. Structured observation diagnostics become inaccessible.
- Event mapStoredEvent (`api/mapping.ts:83`) drops sequence/schema_version/parent_event_id/causation_id/correlation_id. Event actorId/runId retained; JobDetailView's trace does not render them. It derives source.kind='agent' from any actorId even though canonical actorId can name a non-agent actor; preserve known actor classification when available, otherwise avoid asserting kind.
- Capacity summary cachedTokens/totalFailures and per-provider failureBreakdown/statusReason/observedAt/modelId/actorId/input/output/cached/request/token limits/remaining are mapped, but not all represented in the Usage UI. In particular modelId/actorId/observedAt are needed to explain which observation a provider context meter belongs to; provider context is not a fleet or per-agent aggregate. Not every raw field needs its own widget, but a diagnostic/raw-details affordance would prevent meaningful losses.
- Agent presentation animationProfile/badge and null card semantics remain selectively remapped; personas are explicitly outside this milestone. Null characterCardUrl is still replaced by a local asset inference; label this as a local dossier asset, not a fetched runtime dossier.

### Remaining honest gaps / backend scope

- No agent inbox renderer, job recovery diagnostics, standalone thread selector or message pagination. These are frontend gaps, not missing endpoints. Current composer selects first/matching thread and fetches first 50 messages; client conversation filtering is limited to that subset. Do not claim all messages/conversations are shown.
- Job history requests 500 and renders latest 50 of those. Backend canonical list_events uses ascending order before limit, so for >500 stored events the API may return the oldest 500. Full latest-history pagination needs a backend cursor/change; the UI should disclose retention limits now.
- Missing per-agent context and sprint cap/cost/estimator APIs justify unknown or unavailable; this is **WONTFIX(backend)** for this branch, not a defect in showing unknown.
- Agent identity refresh is implemented for the roster but not the selected detail; stream status versus reachable HTTP service remains conflated. Error/freshness/retry states are improved but not uniformly four-state in every inspector or child widget (F2).

## Required regression coverage before approval

Read-only, in-memory execution of the actual TypeScript helpers confirmed: a bus-shaped event passed through mapEvent/mergeJobEvents is labeled `stored`; mapJobTokenTelemetry with null tokens returns four numeric zeros; explainFailure with populated verification results emits only `verification FAILED` and drops the result details. These reproductions wrote no source/test files and made no HTTP requests. Selection/request races and Reply payload loss are source-proven control-flow cases, not claims of live mutation tests.

1. Agent A/B and job A/B selection with out-of-order GET responses; same-job terminal update racing an older response; keyed telemetry fetching B failure must never show A data.
2. Loaded detail/tokens then failed refresh: actual error, retry and stale/freshness indication must remain visible.
3. Reply click then submit: assert exact replyTo/conversationId/correlationId; failed send keeps operator text/context.
4. Populated successful and failed job verification results, repair/replan counts and retryHistory render; no static retry limit.
5. Both canonical and bus-fallback job history: only canonical envelopes may assert durability; IDs/actor/run metadata survive.

The implementation substantially improves M1–M4 truth and wiring. The findings above are reachable with existing API contracts and ordinary UI interactions, so sparse current live data and passing fixture tests do not justify MERGE OK yet.
