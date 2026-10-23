import { HermesApi, EventSubscription } from '../contracts';
import {
  AgentId,
  AgentSummary,
  AgentDetail,
  Job,
  JobDetail,
  PipelineStep,
  JobPhase,
  ProjectionItem,
  CapacityTelemetry,
  AgentLimitsReport,
  JobTokenTelemetry,
  RunReview,
  TaskNode,
  AgentRun,
  JobObservation,
  SettingItem,
  TraceEvent,
  OverviewTelemetry,
  Thread,
  Message,
  MailboxEntry,
  ExecutionSnapshot,
  AgentModelsMap,
  SetAgentModelResponse
} from '../types';
import { MOCK_AGENTS, createDynamicMockAgent } from '../mock/agents';
import { MOCK_AGENT_MODELS } from '../mock/models';
import { MOCK_JOBS, MOCK_ACTIVE_JOB_DETAIL } from '../mock/jobs';
import { mapPhaseState } from './httpAdapter';
import {
  MOCK_TELEMETRY,
  MOCK_PROJECTIONS,
  MOCK_RUNTIME_SETTINGS,
  MOCK_POLICY_SETTINGS
} from '../mock/telemetry';
import { RAW_SEED_EVENTS, RAW_POOL_EVENTS } from '../mock/events';
import {
  createMockExecutionHistory,
  createMockExecutionScript,
  createMockExecutionSnapshot
} from '../mock/execution';
import { resolveActorPresentation } from '../actors';

// Deliberately long values are always present in mock mode, including browser layout checks.
export const LONG_PROMPT_PATH = '/home/lystiger/Projects/Hermes-lab/prompts/' + 'summary-first-console-'.repeat(2) + 'builder-run.md';
export const LONG_JOB_ID = 'run_20261019_115655_' + 'lyscontrol-m10-summary-first-layout-fixture'.slice(0, 40).padEnd(40, 'x');
export const LONG_TEXT_JOB: Job = {
  // Queued, so mock mode still has exactly one active job (#142), matching the mock telemetry counts.
  ...MOCK_JOBS[1], id: LONG_JOB_ID, title: LONG_PROMPT_PATH, status: 'QUEUED'
};
export const LONG_TEXT_EVENT: TraceEvent = {
  id: 'long-text-event', ts: '10:42:47.400', rawTs: 38567.4,
  source: { id: 'scheduler-fixture', kind: 'runtime', displayName: 'Hermes.scheduler' },
  kind: 'task.created', detail: LONG_PROMPT_PATH, jobId: LONG_JOB_ID, dur: '—'
};

/** Same mapping as HttpHermesApi.getJob: one execution-graph step per Hermes phase. */
function phaseSteps(jobId: string, phases: JobPhase[]): PipelineStep[] {
  return phases.map((p) => ({
    id: p.id,
    jobId,
    phase: p.name,
    agentId: p.agentId,
    task: p.name,
    meta: p.commitSha ? p.commitSha.slice(0, 7) : p.status.toLowerCase(),
    state: mapPhaseState(p.status),
    note: p.role
  }));
}

function fmtTs(sec: number): string {
  const h = Math.floor(sec / 3600);
  const m = Math.floor(sec / 60) % 60;
  const s = Math.floor(sec % 60);
  const ms = Math.round((sec - Math.floor(sec)) * 1000);
  const pad = (n: number, w: number) => String(n).padStart(w, '0');
  return `${pad(h, 2)}:${pad(m, 2)}:${pad(s, 2)}.${pad(ms, 3)}`;
}

export class MockHermesApi implements HermesApi {
  private agents: Record<AgentId, AgentDetail> = { ...MOCK_AGENTS };
  private agentModels: AgentModelsMap = JSON.parse(JSON.stringify(MOCK_AGENT_MODELS));
  private jobs: Job[] = [LONG_TEXT_JOB, ...MOCK_JOBS];
  private simTick = 0;
  private lastSimTs = 10 * 3600 + 42 * 60 + 47.4;
  private execSeq = 0;
  async getHealth() {
    return {
      status: 'ok',
      service: 'hermes-mock',
      version: '0.1.0-mock',
      uptimeSeconds: 4200,
      timestamp: new Date().toISOString()
    };
  }

  async getAgents(): Promise<AgentSummary[]> {
    return Object.values(this.agents).map((detail) => ({
      id: detail.id,
      displayName: detail.displayName,
      provider: detail.provider,
      model: detail.model,
      role: detail.role,
      capabilities: detail.capabilities,
      status: detail.status,
      phase: detail.phase,
      presentation: detail.presentation,
      currentTask: detail.currentTask,
      activeTool: detail.activeTool,
      contextPct: detail.contextPct,
      contextUsed: detail.contextUsed,
      contextMax: detail.contextMax,
      queueDepth: detail.queueDepth,
      sessionTokens: detail.sessionTokens
    }));
  }

  async getAgent(id: AgentId): Promise<AgentDetail | null> {
    const normalized = id.toLowerCase();
    if (this.agents[normalized]) {
      return { ...this.agents[normalized] };
    }
    // Return dynamically generated fallback model for unknown agent IDs (e.g. Kimi, subagents)
    return createDynamicMockAgent(
      id,
      id.charAt(0).toUpperCase() + id.slice(1),
      'Dynamic Provider',
      `${id}-model`,
      'Specialized Dynamic Operative'
    );
  }

  async getJobs(): Promise<Job[]> {
    return [...this.jobs];
  }

  async getJob(id: string): Promise<JobDetail | null> {
    if (id === '#142' || id === '142') {
      return { ...MOCK_ACTIVE_JOB_DETAIL, executionGraph: phaseSteps(MOCK_ACTIVE_JOB_DETAIL.id, MOCK_ACTIVE_JOB_DETAIL.phases ?? []) };
    }
    const found = this.jobs.find((j) => j.id === id);
    if (!found) return null;

    // Like Hermes, a job that has not started reports only the phases it was created with.
    const phases: JobPhase[] = id === LONG_JOB_ID ? [{ id: 'long-phase', order: 1, role: 'builder', name: LONG_PROMPT_PATH, status: 'PENDING', agentId: 'codex' }] : [];
    return {
      ...found,
      phases,
      executionGraph: phaseSteps(id, phases),
      changedFiles: [],
      retryHistory: [],
      retriesUsed: 0,
      maxRetries: 3,
      tokenBreakdown: []
    };
  }

  /** Steps of every active mock job, built from its phases the way the HTTP adapter builds them. */
  async getPipeline(): Promise<PipelineStep[]> {
    return phaseSteps(MOCK_ACTIVE_JOB_DETAIL.id, MOCK_ACTIVE_JOB_DETAIL.phases ?? []);
  }

  async getTelemetry(): Promise<OverviewTelemetry> {
    return { ...MOCK_TELEMETRY };
  }

  // M2 endpoints: mock fixtures carry no capacity, task, run or observation records.
  async getCapacityTelemetry(): Promise<CapacityTelemetry> {
    return { timestamp: null, summary: null, providers: [], jobsTracked: 0 };
  }

  async getAgentLimits(): Promise<AgentLimitsReport> {
    return {
      timestamp: '2026-10-20T08:00:00Z',
      agents: [
        {
          id: 'claude', name: 'Claude', plan: 'Max 5x', ready: true, stale: false, status: 'ok',
          usedPct: 14, leftPct: 86, resetsAt: '2026-10-20T10:10:00Z', resetsInSeconds: 7800,
          windows: [
            { label: '5h', usedPct: 14, leftPct: 86, resetsAt: '2026-10-20T10:10:00Z', resetsInSeconds: 7800 },
            { label: 'Weekly', usedPct: 6, leftPct: 94, resetsAt: '2026-10-25T08:00:00Z', resetsInSeconds: 432000 }
          ],
          updatedAt: '2026-10-20T07:59:00Z', authHelp: ''
        },
        {
          id: 'codex', name: 'Codex', plan: '', ready: false, stale: false, status: 'ok',
          usedPct: 0, leftPct: 100, resetsAt: null, resetsInSeconds: 0, windows: [],
          updatedAt: '2026-10-20T07:59:00Z', authHelp: 'Run `codex login` to sign in.'
        }
      ]
    };
  }

  async getReviews(): Promise<RunReview[]> {
    // MOCK: one finished run, shaped like GET /reviews, so the Review page has something to show offline.
    return [{
      jobId: 'run_mock_review',
      goal: 'Add a read-only Live floor page at /floor that shows which agents are doing what right now.',
      branch: 'job/run_mock_review/integration',
      repairs: 1,
      tasks: [
        { id: 'floor_layout_helper', role: 'builder', agent: 'claude', status: 'SUCCEEDED' },
        { id: 'floor_vitest_coverage', role: 'hardener', agent: 'codex', status: 'SUCCEEDED' },
        { id: 'floor_final_verification', role: 'verifier', agent: 'codex', status: 'SUPERSEDED' },
        { id: 'repair_floor_final_verification_1', role: 'builder', agent: 'claude', status: 'SUCCEEDED' },
        { id: 'recheck_floor_final_verification_1', role: 'verifier', agent: 'codex', status: 'SUCCEEDED' }
      ],
      verdict: { task: 'recheck_floor_final_verification_1', summary: 'Typecheck, lint, tests and build pass.', findings: [] },
      costUsd: 0.0465,
      totalTokens: 1_310_000,
      prUrl: 'https://github.com/lystiger/Hermes-lab/pull/23',
      prState: 'OPEN',
      finishedAt: new Date(Date.now() - 3 * 3_600_000).toISOString()
    }];
  }

  async getJobTelemetry(jobId: string): Promise<JobTokenTelemetry> {
    return { jobId, inputTokens: 0, outputTokens: 0, cachedTokens: 0, totalTokens: 0, costUsd: null, tasks: [] };
  }

  async getJobTasks(_jobId: string): Promise<TaskNode[]> {
    return [];
  }

  async getJobRuns(_jobId: string): Promise<AgentRun[]> {
    return [];
  }

  async getJobObservations(_jobId: string): Promise<JobObservation[]> {
    return [];
  }

  async getJobEvents(jobId: string): Promise<TraceEvent[]> {
    return jobId === LONG_JOB_ID ? [LONG_TEXT_EVENT] : [];
  }

  async getRecoverableJobs(): Promise<Job[]> {
    const jobs = await this.getJobs();
    return jobs.filter((j) => j.status !== 'COMPLETED' && j.status !== 'CANCELLED');
  }

  async getProjections(): Promise<ProjectionItem[]> {
    return [...MOCK_PROJECTIONS];
  }

  async getSettings(): Promise<{ runtime: SettingItem[]; policy: SettingItem[] }> {
    return {
      runtime: [...MOCK_RUNTIME_SETTINGS],
      policy: [...MOCK_POLICY_SETTINGS]
    };
  }

  async getExecutionSnapshot(): Promise<ExecutionSnapshot> {
    return createMockExecutionSnapshot();
  }

  async getTraceEvents(limit = 20): Promise<TraceEvent[]> {
    const baseTs = 10 * 3600 + 42 * 60 + 16;
    const agentList = Object.values(this.agents);

    const seeds = RAW_SEED_EVENTS.slice(0, limit).map((e, idx) => ({
      id: `seed-${idx}`,
      ts: fmtTs(baseTs + (e.t ?? 0)),
      rawTs: baseTs + (e.t ?? 0),
      source: resolveActorPresentation(e.a, agentList),
      kind: e.k,
      detail: e.d,
      dur: e.dur || '—',
      jobId: '#142',
      metadata: e.m
    })).reverse();

    return [LONG_TEXT_EVENT, ...seeds, ...createMockExecutionHistory(fmtTs)];
  }

  subscribeEvents(
    handler: (event: TraceEvent) => void,
    _onError?: (err: Error) => void,
    _initialCursor?: string
  ): EventSubscription {
    const agentList = Object.values(this.agents);

    // Scripted execution lifecycles (subprocess) on a slower cadence than the agent pool.
    let execQueue: TraceEvent[] = [];
    const execTimer = setInterval(() => {
      if (execQueue.length === 0) {
        this.execSeq += 1;
        execQueue = createMockExecutionScript(this.execSeq, this.lastSimTs, fmtTs);
      }
      const next = execQueue.shift();
      if (next) handler(next);
    }, 4000);

    const timer = setInterval(() => {
      this.simTick += 1;
      const p = RAW_POOL_EVENTS[this.simTick % RAW_POOL_EVENTS.length];
      const ts = this.lastSimTs + 0.4 + ((this.simTick * 37) % 130) / 100;
      this.lastSimTs = ts;

      const event: TraceEvent = {
        id: `mock-evt-${this.simTick}-${Date.now()}`,
        ts: fmtTs(ts),
        rawTs: ts,
        source: resolveActorPresentation(p.a, agentList),
        kind: p.k,
        detail: p.d,
        dur: p.dur || '—',
        jobId: '#142'
      };

      handler(event);
    }, 2000);

    return {
      unsubscribe: () => {
        clearInterval(timer);
        clearInterval(execTimer);
      }
    };
  }

  async sendOperatorCommand(targetActorId: string, command: string): Promise<{ success: boolean; response: string }> {
    return {
      success: true,
      response: `[Hermes / ${targetActorId}] Dispatched: "${command}". Processed by mock adapter.`
    };
  }

  async triggerJobAction(jobId: string, action: 'retry' | 'pause' | 'cancel' | 'promote'): Promise<boolean> {
    console.log(`[MockHermesApi] Action '${action}' on job ${jobId}`);
    return true;
  }
  // --------------------------------------------------------------------------
  // Phase 5 Operational Messaging & Threads (Mock)
  // --------------------------------------------------------------------------

  private mockThreads: Thread[] = [
    {
      id: "thread_job_#142",
      jobId: "#142",
      title: "Sprint #142 Execution",
      participants: [
        { id: "gemini", kind: "agent", displayName: "Gemini", accentColor: "#5B8CFF" },
        { id: "claude", kind: "agent", displayName: "Claude", accentColor: "#D9A05B" },
        { id: "codex", kind: "agent", displayName: "Codex", accentColor: "#3FB950" },
        { id: "hermes", kind: "runtime", displayName: "Hermes", accentColor: "#CBA35C" }
      ],
      createdAt: "2026-08-22T10:40:00Z",
      updatedAt: "2026-08-22T10:42:17Z"
    }
  ];

  private mockMessages: Message[] = [
    {
      id: "msg_mock_001",
      threadId: "thread_job_#142",
      from: { id: "gemini", kind: "agent", displayName: "Gemini", accentColor: "#5B8CFF", subtitle: "Energetic Builder" },
      to: [{ id: "claude", kind: "agent", displayName: "Claude", accentColor: "#D9A05B", subtitle: "Calm Hardener" }],
      kind: "handoff",
      intent: "review_request",
      conversationId: "conv_sprint_142_review",
      text: "BUILD implementation complete. Commit 8a21fc9. Please review scheduler mutex lock implementation.",
      jobId: "#142",
      phaseId: "phase-1-build",
      artifactRefs: [
        { id: "art_m1", type: "git_commit", label: "BUILD commit", ref: "8a21fc9", trust: { status: "not_applicable", kind: "git_reference", scope: "target_repository", detail: "Git commit reference" } },
        { id: "art_m2", type: "handoff", label: "BUILD handoff", ref: "HANDOFF_BUILD.md", trust: { status: "verified", kind: "path_containment", scope: "hermes_run_root", detail: "Contained within Hermes run root" } }
      ],
      createdAt: "2026-08-22T10:41:05Z"
    },
    {
      id: "msg_mock_002",
      threadId: "thread_job_#142",
      from: { id: "claude", kind: "agent", displayName: "Claude", accentColor: "#D9A05B", subtitle: "Calm Hardener" },
      to: [{ id: "gemini", kind: "agent", displayName: "Gemini", accentColor: "#5B8CFF", subtitle: "Energetic Builder" }],
      kind: "a2a",
      intent: "correction_request",
      conversationId: "conv_sprint_142_review",
      replyTo: "msg_mock_001",
      correlationId: "corr_142_01",
      text: "Found state cleanup race in reset_state(). Please acquire mutex lock prior to state flush.",
      jobId: "#142",
      phaseId: "phase-2-harden",
      createdAt: "2026-08-22T10:41:25Z"
    },
    {
      id: "msg_mock_003",
      threadId: "thread_job_#142",
      from: { id: "gemini", kind: "agent", displayName: "Gemini", accentColor: "#5B8CFF", subtitle: "Energetic Builder" },
      to: [{ id: "claude", kind: "agent", displayName: "Claude", accentColor: "#D9A05B", subtitle: "Calm Hardener" }],
      kind: "a2a",
      intent: "correction_result",
      conversationId: "conv_sprint_142_review",
      replyTo: "msg_mock_002",
      correlationId: "corr_142_01",
      text: "Resolved in commit 91cf33a. Mutex is now acquired prior to reset_state().",
      jobId: "#142",
      phaseId: "phase-1-build",
      createdAt: "2026-08-22T10:41:40Z"
    },
    {
      id: "msg_mock_004",
      threadId: "thread_job_#142",
      from: { id: "claude", kind: "agent", displayName: "Claude", accentColor: "#D9A05B", subtitle: "Calm Hardener" },
      to: [{ id: "codex", kind: "agent", displayName: "Codex", accentColor: "#3FB950", subtitle: "Precision Verifier" }],
      kind: "handoff",
      intent: "verification_request",
      conversationId: "conv_sprint_142_review",
      replyTo: "msg_mock_003",
      text: "HARDEN complete. Race condition resolved and verified. Ready for verification suite.",
      jobId: "#142",
      phaseId: "phase-2-harden",
      artifactRefs: [
        { id: "art_m3", type: "git_commit", label: "HARDEN commit", ref: "91cf33a", trust: { status: "not_applicable", kind: "git_reference", scope: "target_repository", detail: "Git commit reference" } },
        { id: "art_m4", type: "handoff", label: "HARDEN handoff", ref: "HANDOFF_CLAUDE.md", trust: { status: "verified", kind: "path_containment", scope: "hermes_run_root", detail: "Contained within Hermes run root" } }
      ],
      createdAt: "2026-08-22T10:41:55Z"
    },
    {
      id: "msg_mock_005",
      threadId: "thread_job_#142",
      from: { id: "codex", kind: "agent", displayName: "Codex", accentColor: "#3FB950", subtitle: "Precision Verifier" },
      to: [{ id: "hermes", kind: "runtime", displayName: "Hermes", accentColor: "#CBA35C" }],
      kind: "verification_result",
      intent: "verification_result",
      conversationId: "conv_sprint_142_review",
      replyTo: "msg_mock_004",
      text: "VERIFY passed: 42 tests passed, 0 failed, 0 regressions.",
      jobId: "#142",
      phaseId: "phase-3-verify",
      artifactRefs: [
        { id: "art_m5", type: "test_report", label: "Verification result", ref: "verification.json", trust: { status: "verified", kind: "path_containment", scope: "hermes_run_root", detail: "Contained within Hermes run root" } }
      ],
      createdAt: "2026-08-22T10:42:17Z"
    }
  ];

  async getThreads(jobId?: string, participant?: string, limit?: number): Promise<Thread[]> {
    let threads = [...this.mockThreads];
    if (jobId) {
      threads = threads.filter((t) => t.jobId === jobId || t.id.includes(jobId));
    }
    if (participant) {
      threads = threads.filter((t) => t.participants.some((p) => p.id === participant.toLowerCase()));
    }
    return threads.slice(0, limit || 50);
  }

  async getThread(threadId: string): Promise<Thread | null> {
    const found = this.mockThreads.find((t) => t.id === threadId || (t.jobId && threadId.includes(t.jobId)));
    return found ? { ...found } : null;
  }

  async getMessages(threadId: string, limit?: number, after?: string, conversationId?: string): Promise<Message[]> {
    let msgs = this.mockMessages.filter((m) => m.threadId === threadId || (threadId.includes(m.jobId || "---")));
    if (conversationId) {
      msgs = msgs.filter((m) => m.conversationId === conversationId);
    }
    if (after) {
      const idx = msgs.findIndex((m) => m.id === after);
      if (idx !== -1) msgs = msgs.slice(idx + 1);
    }
    return msgs.slice(0, limit || 50);
  }

  async getAgentInbox(agentId: string, state?: string, limit?: number, conversationId?: string): Promise<MailboxEntry[]> {
    const norm = agentId.toLowerCase();
    let msgs = this.mockMessages.filter((m) => m.to.some((t) => t.id === norm));
    if (conversationId) {
      msgs = msgs.filter((m) => m.conversationId === conversationId);
    }
    const entries: MailboxEntry[] = msgs.map((m) => ({
      messageId: m.id,
      recipientId: norm,
      state: "DELIVERED",
      receivedAt: m.createdAt,
      message: m
    }));
    return entries.slice(0, limit || 50);
  }

  async sendMessage(
    threadId: string,
    text: string,
    to?: string[],
    kind?: string,
    intent?: string,
    conversationId?: string,
    replyTo?: string,
    correlationId?: string
  ): Promise<Message> {
    const newMsg: Message = {
      id: `msg_mock_${Date.now()}`,
      threadId,
      from: { id: "operator", kind: "operator", displayName: "Operator", accentColor: "#E6E9ED", subtitle: "Human Operator" },
      to: (to || ["hermes"]).map((id) => resolveActorPresentation(id)),
      kind: kind || "operator",
      intent,
      conversationId,
      replyTo,
      correlationId,
      text,
      createdAt: new Date().toISOString()
    };
    this.mockMessages.push(newMsg);
    return newMsg;
  }

  // --------------------------------------------------------------------------
  // M8 Agent Model Registry
  // --------------------------------------------------------------------------

  async getAgentModels(): Promise<AgentModelsMap> {
    return JSON.parse(JSON.stringify(this.agentModels));
  }

  async setAgentModel(agentId: string, model: string, effort?: string | null): Promise<SetAgentModelResponse> {
    const id = agentId.toLowerCase();
    const config = this.agentModels[id];
    if (!config) {
      throw new Error(`Unknown agent: ${agentId}`);
    }
    if (!config.allowed.includes(model)) {
      throw new Error(`Model '${model}' is not allowed for ${agentId}`);
    }
    config.configured = {
      default: model,
      effort: effort !== undefined ? effort : null
    };
    return {
      default: model,
      effort: effort !== undefined ? effort : null
    };
  }
}

