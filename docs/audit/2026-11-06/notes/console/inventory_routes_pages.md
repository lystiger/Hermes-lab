# Console Inventory: Routes, Pages, and Top-Level Views

Audit date: 2026-11-06  
Auditor role: Hardener  
Target codebase: `console/`  
Objective: Catalog every route, page, and top-level view in the operator console. Record defining `file:line`, supported operator decision, code quotes, and whether each item helps run or verify jobs.

---

## 1. Executive Summary & Inventory Matrix

| Route / View | Component | Defined At (Route & Component) | Operator Decision Supported | Helps Run or Verify Jobs? |
|---|---|---|---|---|
| `/` | `OverviewRoute` | [`App.tsx:21`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/App.tsx#L21), [`index.tsx:30`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/routes/index.tsx#L30) | What needs urgent intervention (failures, blocked/paused runs, open PRs) | **YES** (Triage & intervention entry) |
| `/queue` | `QueueRoute` | [`App.tsx:22`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/App.tsx#L22), [`queue.tsx:16`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/routes/queue.tsx#L16) | What work is pending, running, failed, or recoverable | **YES** (Queue management & recovery) |
| `/agents` | `AgentsListRoute` | [`App.tsx:23`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/App.tsx#L23), [`agents/index.tsx:108`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/routes/agents/index.tsx#L108) | Which model and reasoning effort each agent uses for upcoming execution phases | **YES** (Runtime execution parameter tuning) |
| `/agents/:agentId` | `AgentDetailRoute` | [`App.tsx:24`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/App.tsx#L24), [`agents/$agentId.tsx:6`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/routes/agents/$agentId.tsx#L6) | Inspecting agent identity, persona description, running phase strip, and prompt details | **MARGINAL / NO** (Agent profile viewer; running phases strip repeats floor/overview) |
| `/usage` | `UsageRoute` | [`App.tsx:25`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/App.tsx#L25), [`usage.tsx:76`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/routes/usage.tsx#L76) | Whether quota, token depletion, or throttling will stall jobs; explains capacity pauses | **YES** (Prevents/explains `WAITING_FOR_CAPACITY` job stalls) |
| `/events` | `EventsRoute` | [`App.tsx:26`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/App.tsx#L26), [`events.tsx:19`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/routes/events.tsx#L19) | Low-level bus diagnostic: inspecting stream health, event payloads, error stacktraces | **YES** (Job failure root-cause verification) |
| `/execution` | `ExecutionRoute` | [`App.tsx:27`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/App.tsx#L27), [`execution.tsx:11`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/routes/execution.tsx#L11) | Whether execution backends (herdr, sandboxes) are available to run jobs | **YES** (Verifies runtime sandbox readiness) |
| `/comms` | `CommsRoute` | [`App.tsx:28`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/App.tsx#L28), [`comms.tsx:14`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/routes/comms.tsx#L14) | Interactive chat to draft project briefs ("can't start or merge anything") | **NO** (Does not run or verify jobs; isolated brief drafting chat) |
| `/design` | `DesignRoute` | [`App.tsx:29`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/App.tsx#L29), [`design.tsx:38`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/routes/design.tsx#L38) | Choosing visual aesthetic direction for project Unigreen | **NO** (Static visual design moodboard selector) |
| `/floor` | `FloorRoute` | [`App.tsx:30`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/App.tsx#L30), [`floor.tsx:20`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/routes/floor.tsx#L20) | Real-time active job monitoring across phases, dependency columns, repairs, and spend | **YES** (Core live job progress tracking) |
| `/review` | `ReviewRoute` | [`App.tsx:31`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/App.tsx#L31), [`review.tsx:15`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/routes/review.tsx#L15) | Verifying completed goal runs, verifier verdicts, repair counts, and deciding whether to open/merge PRs | **YES** (Core job verification and PR approval) |
| `/settings` | `SettingsRoute` | [`App.tsx:32`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/App.tsx#L32), [`settings.tsx:8`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/routes/settings.tsx#L8) | Viewing static environment parameters, toggling 3D client motion rings, jumping to design | **NO** (Client appearance toggle & static display; no job management) |
| `*` (Catch-all) | `Navigate to="/"` | [`App.tsx:33`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/App.tsx#L33) | Fallback recovery routing on invalid URL | **INDIRECT** (Route guard) |
| App Shell | `Layout` | [`Layout.tsx:11`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/components/Layout.tsx#L11) | Global container: hosts event stream subscription, D-009 snapshot loader, banners, and modals | **YES** (Global harness & runtime data lifeline) |
| Sidebar Navigation | `Sidebar` | [`Sidebar.tsx:67`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/components/Sidebar.tsx#L67) | High-level domain navigation and quick triage via live badge counters (queue count, active execution) | **YES** (Navigation + real-time status signals) |
| Breadcrumb Header | `Header` | [`Header.tsx:5`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/components/Header.tsx#L5) | Back navigation link from `/agents/:agentId` to `/agents` | **NO** (Narrow navigation helper for single sub-page) |
| Connection Banner | `ConnectionBanner` | [`ConnectionBanner.tsx:11`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/components/ConnectionBanner.tsx#L11) | Detecting broken API connectivity and initiating immediate manual state resync | **YES** (Operational safety; alerts to stale/disconnected state) |
| Job Inspector Modal | `JobModal` / `JobDetailView` | [`JobModal.tsx:8`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/components/JobModal.tsx#L8), [`JobDetailView.tsx:19`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/features/jobs/JobDetailView.tsx#L19) | Deep diagnostic inspection of a job: failure diagnosis, timeline phases, task execution, thread messages | **YES** (Primary diagnostic tool for job failures and verification) |
| Operative Dossier Modal | `DossierModal` | [`DossierModal.tsx:6`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/components/DossierModal.tsx#L6) | Character card image viewing | **NO** (Pure aesthetic character artwork presentation) |

---

## 2. Detailed Route Inventory

### 2.1 Route: `/` (Dashboard / Overview)
- **Route Registration**: [`console/src/App.tsx:21`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/App.tsx#L21)
  ```tsx
  <Route index element={<OverviewRoute />} />
  ```
- **Component Definition**: [`console/src/routes/index.tsx:30`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/routes/index.tsx#L30)
  ```tsx
  /**
   * What needs the operator: failed, blocked and paused runs and open pull requests first, then what is running
   * and the agents. Details live on the Floor (runs), Review (finished runs), Queue (backlog) and Events (log).
   */
  export const OverviewRoute: React.FC = () => {
  ```
- **Operator Decision Supported**:
  Prioritizes what needs the operator immediately. Directly surfaces failed runs, blocked jobs, jobs paused waiting for agent capacity (`WAITING_FOR_CAPACITY`), and finished runs with open pull requests pending review.
- **Helps Run or Verify Jobs**:
  **YES**. Direct triage entry point. Allows one-click routing to open jobs, floor tracking, or reviewing completed pull requests.

---

### 2.2 Route: `/queue` (Queue & Backlog)
- **Route Registration**: [`console/src/App.tsx:22`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/App.tsx#L22)
  ```tsx
  <Route path="queue" element={<QueueRoute />} />
  ```
- **Component Definition**: [`console/src/routes/queue.tsx:16`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/routes/queue.tsx#L16)
  ```tsx
  export const QueueRoute: React.FC = () => {
    const { setActiveModalJobId } = useConsoleStore();
    const { jobs, loading: jobsLoading, error: jobsError, stale, updatedAt: jobsUpdatedAt, refetch: refetchJobs } = useJobs();
  ```
- **Operator Decision Supported**:
  Supports inspecting historical runs, backlog depth, queued jobs, and identifying recoverable jobs that stopped prematurely or need attention.
- **Helps Run or Verify Jobs**:
  **YES**. Lets operators inspect all jobs in the mission board, verify job states, and open recoverable jobs for inspection.

---

### 2.3 Route: `/agents` (Agents List & Model Selector)
- **Route Registration**: [`console/src/App.tsx:23`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/App.tsx#L23)
  ```tsx
  <Route path="agents" element={<AgentsListRoute />} />
  ```
- **Component Definition**: [`console/src/routes/agents/index.tsx:107-108`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/routes/agents/index.tsx#L107-L108)
  ```tsx
  /** /agents: a plain list of agents with their provider, model and reasoning effort, and a picker to change them. */
  export const AgentsListRoute: React.FC = () => {
  ```
- **Operator Decision Supported**:
  Enables the operator to reconfigure the LLM provider model and reasoning effort tier for each agent (e.g. Claude, Codex, Gemini) before the next phase runs (`hermesApi.setAgentModel(agent.id, currentModel, currentEffort)` at line 44).
- **Helps Run or Verify Jobs**:
  **YES**. Allows live steering of model capability and reasoning effort for subsequent job execution phases.

---

### 2.4 Route: `/agents/:agentId` (Agent Detail Workspace)
- **Route Registration**: [`console/src/App.tsx:24`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/App.tsx#L24)
  ```tsx
  <Route path="agents/:agentId" element={<AgentDetailRoute />} />
  ```
- **Component Definition**: [`console/src/routes/agents/$agentId.tsx:5-9`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/routes/agents/$agentId.tsx#L5-L9)
  ```tsx
  /** /agents/:agentId: roster with this agent's dossier open. */
  export const AgentDetailRoute: React.FC = () => {
    const { agentId } = useParams<{ agentId: string }>();
    return <AgentWorkspace selectedId={agentId} />;
  };
  ```
- **Nested Workspace Definition**: [`console/src/features/agents/AgentWorkspace.tsx:10-14`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/features/agents/AgentWorkspace.tsx#L10-L14)
  ```tsx
  /**
   * Roster on the left, dossier of the selected agent on the right (research §5.1). The route decides the
   * selection: /agents picks the first agent, /agents/:id picks that agent.
   */
  export const AgentWorkspace: React.FC<{ selectedId?: string }> = ({ selectedId }) => {
  ```
- **Operator Decision Supported**:
  Inspects detailed dossier information for an agent: lore description, character portrait, system prompt instructions, capabilities list, context meter, and running phases strip.
- **Helps Run or Verify Jobs**:
  **MARGINAL / NO**. Does not trigger, pause, or verify runs. The running phases strip displays active work, but this duplicates data already present on `/floor` and `/`.

---

### 2.5 Route: `/usage` (Agent Capacity & Limits)
- **Route Registration**: [`console/src/App.tsx:25`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/App.tsx#L25)
  ```tsx
  <Route path="usage" element={<UsageRoute />} />
  ```
- **Component Definition**: [`console/src/routes/usage.tsx:75-76`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/routes/usage.tsx#L75-L76)
  ```tsx
  /** Usage: what is left for each agent, as computed by Hermes, plus the runtime totals in the header. */
  export const UsageRoute: React.FC = () => {
  ```
- **Operator Decision Supported**:
  Assesses whether agent rate limits, rolling token windows, or throttling events are exhausting provider capacity. Determines when reset timers will lapse to unblock paused jobs.
- **Helps Run or Verify Jobs**:
  **YES**. Informs the operator why jobs are stuck in `WAITING_FOR_CAPACITY` and provides remaining quotas and reset times.

---

### 2.6 Route: `/events` (Live Event Bus Buffer)
- **Route Registration**: [`console/src/App.tsx:26`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/App.tsx#L26)
  ```tsx
  <Route path="events" element={<EventsRoute />} />
  ```
- **Component Definition**: [`console/src/routes/events.tsx:19`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/routes/events.tsx#L19)
  ```tsx
  export const EventsRoute: React.FC = () => {
    const { allEvents, setActiveModalJobId, connectionStatus } = useConsoleStore();
  ```
- **Operator Decision Supported**:
  Enables low-level forensic debugging of runtime actions. Filters events by category (failures, warnings, execution, agent messages) and source to diagnose unexpected behaviors or job crashes.
- **Helps Run or Verify Jobs**:
  **YES**. Crucial for verifying exact error messages, tool calls, and event payloads when a job fails.

---

### 2.7 Route: `/execution` (Backend Runtime & Sandboxes)
- **Route Registration**: [`console/src/App.tsx:27`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/App.tsx#L27)
  ```tsx
  <Route path="execution" element={<ExecutionRoute />} />
  ```
- **Component Definition**: [`console/src/routes/execution.tsx:11`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/routes/execution.tsx#L11)
  ```tsx
  export const ExecutionRoute: React.FC = () => {
    const { view, snapshotStatus, snapshotError, snapshotLoadedAt, refresh } = useExecution();
  ```
- **Operator Decision Supported**:
  Verifies backend sandbox availability (e.g. herdr CLI presence on PATH) and displays recent execution events. Allows operator to determine whether the sandbox host can accept jobs.
- **Helps Run or Verify Jobs**:
  **YES**. Confirms execution backend infrastructure is functional before/during dispatch.

---

### 2.8 Route: `/comms` (Orchestrator Planning Chat)
- **Route Registration**: [`console/src/App.tsx:28`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/App.tsx#L28)
  ```tsx
  <Route path="comms" element={<CommsRoute />} />
  ```
- **Component Definition**: [`console/src/routes/comms.tsx:10-14`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/routes/comms.tsx#L10-L14)
  ```tsx
  /**
   * Comms: a chat with the orchestrator, laid out like a chat app. The list is on the left, the open
   * chat is in the middle with its model and effort on top, and the composer is at the bottom.
   */
  export const CommsRoute: React.FC = () => {
  ```
  And [`console/src/routes/comms.tsx:185-186`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/routes/comms.tsx#L185-L186):
  ```tsx
  <h2 className="font-display text-[22px] text-lys-primary">What should we plan?</h2>
  <p className="max-w-md text-[13px] text-lys-muted">Ask the orchestrator to draft a brief. It can't start or merge anything.</p>
  ```
- **Operator Decision Supported**:
  Interactive brainstorming and drafting of job briefs with an LLM chat agent. Explicitly isolated from execution.
- **Helps Run or Verify Jobs**:
  **NO**. As the UI explicitly states: *"It can't start or merge anything."* It does not execute jobs, monitor active work, or verify results.

---

### 2.9 Route: `/design` (Unigreen Design Boards)
- **Route Registration**: [`console/src/App.tsx:29`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/App.tsx#L29)
  ```tsx
  <Route path="design" element={<DesignRoute />} />
  ```
- **Component Definition**: [`console/src/routes/design.tsx:5-8, 38`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/routes/design.tsx#L5-L8)
  ```tsx
  /**
   * The design boards for a project. Choosing a direction records it as a human decision in LysStack,
   * through the Hermes API. The page only shows boards and asks for the choice; it does not act on it.
   */
  ...
  export const DesignRoute: React.FC = () => {
  ```
- **Operator Decision Supported**:
  Selects one of three visual aesthetic directions (Clean Eco, Fresh, Japanese Precision) for the Unigreen project.
- **Helps Run or Verify Jobs**:
  **NO**. Project-specific graphic design review board. Does not initiate, monitor, run, or verify jobs.

---

### 2.10 Route: `/floor` (Active Job Floor & Phase Dependency Columns)
- **Route Registration**: [`console/src/App.tsx:30`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/App.tsx#L30)
  ```tsx
  <Route path="floor" element={<FloorRoute />} />
  ```
- **Component Definition**: [`console/src/routes/floor.tsx:16-20`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/routes/floor.tsx#L16-L20)
  ```tsx
  /**
   * The run page: one section per active job, its phases in dependency columns (or on a timeline). A repair
   * sits after the check whose findings it fixes, and its re-check after it. Read-only: it never changes a run.
   */
  export const FloorRoute: React.FC = () => {
  ```
- **Operator Decision Supported**:
  Monitors live job execution in real-time. Tracks phase progression, active agents, repair cycles, and cost accumulation.
- **Helps Run or Verify Jobs**:
  **YES**. Primary operational view for tracking live jobs while running.

---

### 2.11 Route: `/review` (Finished Runs & Pull Requests)
- **Route Registration**: [`console/src/App.tsx:31`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/App.tsx#L31)
  ```tsx
  <Route path="review" element={<ReviewRoute />} />
  ```
- **Component Definition**: [`console/src/routes/review.tsx:11-15`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/routes/review.tsx#L11-L15)
  ```tsx
  /**
   * Finished goal-planned runs, newest first. Hermes opens each run's pull request when it completes;
   * this page is where a human reads what was done and checked before merging. It never merges anything.
   */
  export const ReviewRoute: React.FC = () => {
  ```
- **Operator Decision Supported**:
  Decides whether to merge completed PRs by reading verifier findings, repair history, cost, and task chains.
- **Helps Run or Verify Jobs**:
  **YES**. Core job verification surface before pull requests are approved/merged.

---

### 2.12 Route: `/settings` (Settings & Presentation)
- **Route Registration**: [`console/src/App.tsx:32`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/App.tsx#L32)
  ```tsx
  <Route path="settings" element={<SettingsRoute />} />
  ```
- **Component Definition**: [`console/src/routes/settings.tsx:8, 20-21`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/routes/settings.tsx#L8)
  ```tsx
  export const SettingsRoute: React.FC = () => {
  ...
    return (
      <div className="flex flex-col min-h-full select-none bg-lys-base">
        <PageHeader title="Settings" subtitle="Runtime and presentation" updatedAt={updatedAt} />
  ```
- **Operator Decision Supported**:
  Inspects static runtime environment variables, toggles 3D perspective rings checkbox, lists registered operators, and links to `/design`.
- **Helps Run or Verify Jobs**:
  **NO**. Contains cosmetic options (3D rings toggle) and static readouts. Does not control, run, or verify jobs.

---

### 2.13 Route: `*` (Catch-all Fallback)
- **Route Registration**: [`console/src/App.tsx:33`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/App.tsx#L33)
  ```tsx
  <Route path="*" element={<Navigate to="/" replace />} />
  ```
- **Operator Decision Supported**:
  Recovers gracefully from mistyped or obsolete URLs by redirecting to `/`.
- **Helps Run or Verify Jobs**:
  **INDIRECT**. Prevents blank screen on invalid navigation.

---

## 3. Detailed Top-Level Views & Persistent Shell Overlays

### 3.1 App Layout Container (`Layout`)
- **Component Definition**: [`console/src/components/Layout.tsx:11, 19-45`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/components/Layout.tsx#L11)
  ```tsx
  export const Layout: React.FC = () => {
    const location = useLocation();
    useEventStream();
    useExecutionSnapshotLoader();

    return (
      <div className="flex h-screen min-h-screen bg-lys-base text-lys-primary text-[13px] overflow-hidden">
        <Sidebar />
        <main className="flex-1 min-w-0 flex flex-col overflow-hidden bg-lys-surface-0">
          {isMockMode && (
            <div role="status" className="px-5 py-1.5 border-b border-lys-subtle bg-lys-warning/12 font-sans text-[11px] tracking-wider text-lys-warning">
              MOCK DATA · fixtures, not live Hermes data
            </div>
          )}
          <ConnectionBanner />
          <Header />
          <div className="lys-scroll flex-1 min-h-0 overflow-y-auto">
            <div key={location.pathname} className="lys-enter min-h-full">
              <Outlet />
            </div>
          </div>
        </main>
        <JobModal />
        <DossierModal />
      </div>
    );
  };
  ```
- **Operator Decision Supported**:
  Structural shell managing background WebSocket SSE stream connections, mock-mode warning, and rendering active overlays.
- **Helps Run or Verify Jobs**:
  **YES (Structural Enabler)**. Hosts global data subscriptions and overlays.

---

### 3.2 Navigation Sidebar (`Sidebar`)
- **Component Definition**: [`console/src/components/Sidebar.tsx:28-54, 67, 104-110`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/components/Sidebar.tsx#L28-L54)
  ```tsx
  const NAV_GROUPS: { label: string; items: NavItem[] }[] = [
    {
      label: 'Overview',
      items: [
        { to: '/', label: 'Dashboard', icon: LayoutDashboard },
        { to: '/queue', label: 'Queue', icon: ListTodo },
        { to: '/review', label: 'Review', icon: GitPullRequestArrow }
      ]
    },
    {
      label: 'Live',
      items: [
        { to: '/floor', label: 'Floor', icon: Radar },
        { to: '/events', label: 'Events', icon: Logs },
        { to: '/comms', label: 'Comms', icon: MessagesSquare }
      ]
    },
    {
      label: 'System',
      items: [
        { to: '/agents', label: 'Agents', icon: Users },
        { to: '/usage', label: 'Usage', icon: Gauge },
        { to: '/execution', label: 'Execution', icon: Server },
        { to: '/settings', label: 'Settings', icon: SlidersHorizontal }
      ]
    }
  ];
  ...
  const badges: Record<string, { badge: string; badgeColor?: string } | undefined> = {
    '/queue': !jobsError && jobs.length > 0 ? { badge: String(queueCount) } : undefined,
    '/agents': !agentsError && agents.length > 0 ? { badge: String(agents.length) } : undefined,
    '/events': connectionStatus === 'CONNECTED' ? { badge: 'live', badgeColor: 'var(--lys-status-success)' } : undefined,
    '/execution': activeCount > 0 ? { badge: String(activeCount), badgeColor: 'var(--lys-status-success)' } : undefined
  };
  ```
- **Operator Decision Supported**:
  Enables navigation between console views; badges display pending queue size and active execution count at a glance.
- **Helps Run or Verify Jobs**:
  **YES**. Conveys real-time queue and execution signals without navigating away.

---

### 3.3 Contextual Back Header (`Header`)
- **Component Definition**: [`console/src/components/Header.tsx:5, 17-24`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/components/Header.tsx#L5)
  ```tsx
  export const Header: React.FC = () => {
  ...
    if (pathname.startsWith('/agents/')) {
      title = agent?.displayName || agentId || 'Agent';
      crumb = 'Agents';
      backPath = '/agents';
    }

    // The bar only exists to link back from an agent's page; other pages get the space back.
    if (!crumb) return null;
  ```
- **Operator Decision Supported**:
  Back navigation breadcrumb when inspecting an individual agent at `/agents/:agentId`. Returns `null` on all other routes.
- **Helps Run or Verify Jobs**:
  **NO**. Solely a back-button bar for agent dossiers.

---

### 3.4 Connection Failure Alert Banner (`ConnectionBanner`)
- **Component Definition**: [`console/src/components/ConnectionBanner.tsx:11, 21-38`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/components/ConnectionBanner.tsx#L11)
  ```tsx
  export const ConnectionBanner: React.FC = () => {
    const conn = useConnection();
    if (conn.reachable) return null;
  ...
    return (
      <div
        role="alert"
        className="px-5 py-2.5 border-b border-lys-danger/50 bg-lys-danger/12 font-sans text-[12px] text-lys-danger flex flex-wrap items-center gap-x-4 gap-y-1"
      >
        <span className="font-semibold tracking-wider">CAN'T REACH HERMES</span>
        <span className="text-lys-primary break-all">API {conn.url}</span>
  ```
- **Operator Decision Supported**:
  Warns operator immediately when Hermes API is unreachable, shows last contact timestamp, and allows manual retry.
- **Helps Run or Verify Jobs**:
  **YES**. Prevents operator from acting on stale data during backend disconnections.

---

### 3.5 Job Inspector Modal Overlay (`JobModal` & `JobDetailView`)
- **Modal Definition**: [`console/src/components/JobModal.tsx:8, 20-41`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/components/JobModal.tsx#L8)
  ```tsx
  export const JobModal: React.FC = () => {
    const { activeModalJobId, setActiveModalJobId } = useConsoleStore();
    useEscape(() => setActiveModalJobId(null), activeModalJobId !== null);

    if (!activeModalJobId) return null;
  ...
          <div className="flex-1 overflow-y-auto">
            <JobDetailView jobId={activeModalJobId} />
          </div>
  ```
- **Detail View Definition**: [`console/src/features/jobs/JobDetailView.tsx:19, 103-148`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/features/jobs/JobDetailView.tsx#L19)
  ```tsx
  export const JobDetailView: React.FC<JobDetailViewProps> = ({ jobId = '' }) => {
  ...
        <div className="px-5 pt-4">
          <JobFailure job={job} />
        </div>

        <section aria-label="Run timeline" className="px-5 py-4 border-b border-lys-subtle">
          <JobRunTimeline job={job} />
        </section>
  ...
          <OperationalThreadView jobId={job.id} assignedAgentIds={job.assignedAgentIds} />
          <JobDiagnostics job={job} />
          <JobTasks jobId={job.id} />
          <JobRuns jobId={job.id} />
          <JobObservations jobId={job.id} />
          <JobTaskExecution events={traceRows.map((r) => r.event)} />
  ```
- **Operator Decision Supported**:
  Primary tool for root-cause diagnosis of why a job failed, what tasks and phases completed, which agent executed each step, what artifacts were generated, and what operational messages were passed.
- **Helps Run or Verify Jobs**:
  **YES**. Critical for verifying job outputs, examining failures, and confirming task completion.

---

### 3.6 Operative Dossier Character Card Modal (`DossierModal`)
- **Component Definition**: [`console/src/components/DossierModal.tsx:6, 10-15, 43-49`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/components/DossierModal.tsx#L6)
  ```tsx
  export const DossierModal: React.FC = () => {
    const { activeDossierAgent, setActiveDossierAgent } = useConsoleStore();
    useEscape(() => setActiveDossierAgent(null), activeDossierAgent !== null);

    if (!activeDossierAgent || !activeDossierAgent.presentation?.characterCardUrl) {
      return null;
    }
  ...
          <img
            src={cardUrl}
            alt={`${activeDossierAgent.displayName} Character Card`}
            className="w-full max-h-[78vh] object-contain border border-lys-subtle shadow-lg"
          />
  ```
- **Operator Decision Supported**:
  Displays full-screen character illustration cards for agents.
- **Helps Run or Verify Jobs**:
  **NO**. Aesthetic roleplay/persona illustration viewer. No operational or verification utility.

---

## 4. Architectural Analysis & Route Optimization Candidates

### 4.1 Route Navigation Discrepancies
1. **Unlisted Route (`/design`)**:
   - `/design` exists in [`App.tsx:29`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/App.tsx#L29), but is not in [`Sidebar.tsx`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/components/Sidebar.tsx). It is only reachable via a link buried inside [`SettingsRoute` (`settings.tsx:89`)](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/routes/settings.tsx#L89).
   - *Verdict Candidate*: **CUT**. Dedicated to selecting moodboards for a single sub-project ("Unigreen"); does not run or verify jobs.

2. **Divergent Agent Views (`/agents` vs `/agents/:agentId`)**:
   - [`/agents`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/routes/agents/index.tsx#L108) renders `AgentsListRoute` (a plain table of models and reasoning pickers).
   - [`/agents/:agentId`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/routes/agents/$agentId.tsx#L6) renders `AgentWorkspace` (a split roster + dossier layout with system prompts and character cards).
   - Comment in [`AgentWorkspace.tsx:11-13`](file:///home/lystiger/Work/Hermes/worktrees/run_20261106_215252_c1d1414d/inventory_routes_pages/console/src/features/agents/AgentWorkspace.tsx#L11-L13) assumes `/agents` selects the first agent in `AgentWorkspace`, but `App.tsx` routes `/agents` to `AgentsListRoute`.
   - *Verdict Candidate*: **MERGE**. Model configuration can be merged directly into system execution settings; character lore dossiers can be cut or compressed into a compact tooltip.

3. **Non-operational Routes (`/comms` and `/settings`)**:
   - `/comms`: Explicitly stated as a drafting chat that cannot start, run, or merge jobs.
   - `/settings`: Purely contains static environment reads and a client toggle for 3D perspective rings.
   - *Verdict Candidate*: **CUT** `/comms` and `/design`; **MERGE** necessary `/settings` (runtime info and agent model pickers) into a compact system status overlay or dense panel.

4. **Essential Job Lifecycle Core**:
   - **Run / Triage**: `/` (Overview) + `/floor` (Active Runs) + `/queue` (Backlog & History)
   - **Verify / Approve**: `/review` (PRs & Verifications) + `JobModal` (`JobDetailView`)
   - **Diagnostics**: `/events` (Live error bus) + `/usage` (Rate limits / capacity pauses) + `/execution` (Backend sandboxes)
