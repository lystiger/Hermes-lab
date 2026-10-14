import { HermesApi, EventSubscription } from '../contracts';
import {
  AgentId,
  AgentSummary,
  AgentDetail,
  Job,
  JobDetail,
  PipelineStep,
  ProviderQuota,
  ProjectionItem,
  SettingItem,
  TraceEvent,
  OverviewTelemetry,
  Thread,
  Message,
  MailboxEntry,
  ExecutionSnapshot
} from '../types';
import { MOCK_AGENTS, createDynamicMockAgent } from '../mock/agents';
import { MOCK_JOBS, MOCK_PIPELINE, MOCK_ACTIVE_JOB_DETAIL } from '../mock/jobs';
import {
  MOCK_TELEMETRY,
  MOCK_PROVIDER_QUOTAS,
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
  private jobs: Job[] = [...MOCK_JOBS];
  private pipeline: PipelineStep[] = [...MOCK_PIPELINE];
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
      return { ...MOCK_ACTIVE_JOB_DETAIL };
    }
    const found = this.jobs.find((j) => j.id === id);
    if (!found) return null;

    return {
      ...found,
      executionGraph: this.pipeline.slice(0, 3),
      changedFiles: [],
      retryHistory: [],
      retriesUsed: 0,
      maxRetries: 3,
      tokenBreakdown: []
    };
  }

  async getPipeline(): Promise<PipelineStep[]> {
    return [...this.pipeline];
  }

  async getTelemetry(): Promise<OverviewTelemetry> {
    return { ...MOCK_TELEMETRY };
  }

  async getProviderQuotas(): Promise<ProviderQuota[]> {
    return [...MOCK_PROVIDER_QUOTAS];
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
      ts: fmtTs(baseTs + e.t),
      rawTs: baseTs + e.t,
      source: resolveActorPresentation(e.a, agentList),
      kind: e.k,
      detail: e.d,
      dur: e.dur || '—',
      jobId: '#142'
    })).reverse();

    return [...seeds, ...createMockExecutionHistory(fmtTs)];
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
}

