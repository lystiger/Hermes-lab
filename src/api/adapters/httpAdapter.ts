import { HermesApi, EventSubscription } from '../contracts';
import {
  AgentId,
  AgentSummary,
  AgentDetail,
  Job,
  JobDetail,
  PipelineStep,
  ProjectionItem,
  SettingItem,
  TraceEvent,
  OverviewTelemetry,
  HealthStatus,
  Thread,
  Message,
  MailboxEntry,
  ExecutionSnapshot,
  PipelineStepState,
  CapacityTelemetry,
  JobTokenTelemetry,
  TaskNode,
  AgentRun,
  JobObservation
} from '../types';
import { resolveActorPresentation } from '../actors';
import { HermesUnreachableError, recordContact, recordUnreachable } from '../connection';
import { UNKNOWN } from '../unknown';
import { actorAccent } from '../../theme/agents';
import {
  mapEvent,
  mapCapacityTelemetry,
  mapJobTokenTelemetry,
  mapTaskNode,
  mapAgentRun,
  mapObservation
} from '../mapping';

/** Jobs that are being worked on right now. Anything else is queued, blocked, or terminal. */
export const ACTIVE_JOB_STATUSES = ['RUNNING', 'PLANNING', 'PREPARING', 'VERIFYING', 'REPAIRING'];

const DAY_MS = 24 * 60 * 60 * 1000;

/** Job summary from GET /jobs or GET /jobs/recoverable. Keeps blocked and repair diagnostics; no invented estimates. */
export function mapJobSummary(j: any): Job {
  return {
    id: j.id,
    sprintId: j.sprintId,
    title: j.title,
    repository: j.repository,
    branch: j.branch,
    // Hermes does not report a priority on every job; an absent one stays absent instead of defaulting to P1.
    priority: j.priority || undefined,
    status: j.status,
    currentPhase: j.currentPhase,
    assignedAgentIds: j.assignedAgentIds || [],
    createdAt: j.createdAt,
    startedAt: j.startedAt ?? undefined,
    completedAt: j.completedAt ?? undefined,
    progress: j.progress ?? undefined,
    blockedReason: j.blockedReason ?? null,
    repairCount: j.repairCount ?? 0,
    replanCount: j.replanCount ?? 0,
    estimatedTokens: UNKNOWN,
    estimatedTime: UNKNOWN,
    budget: UNKNOWN
  };
}

/** Maps a backend phase status without collapsing failure, cancellation or skip into BLOCKED or QUEUED. */
export function mapPhaseState(status: string | null | undefined): PipelineStepState {
  switch (status) {
    case 'SUCCEEDED': return 'COMPLETED';
    case 'RUNNING': return 'RUNNING';
    case 'PREPARING': return 'CLAIMED';
    case 'PENDING':
    case 'READY': return 'QUEUED';
    case 'BLOCKED': return 'BLOCKED';
    case 'FAILED': return 'FAILED';
    case 'CANCELLED': return 'CANCELLED';
    case 'SKIPPED': return 'SKIPPED';
    case 'SUPERSEDED': return 'IDLE';
    default: return 'UNKNOWN';
  }
}

interface BackendAgentDTO {
  id: string;
  displayName: string;
  provider: string;
  model: string;
  role: string;
  capabilities: string[];
  status: string;
  phase?: string;
  currentTask?: string;
  activeTool?: string;
  persona?: any;
  presentation?: {
    displayName: string;
    accentColor?: string;
    avatarUrl?: string;
    characterCardUrl?: string;
    sigil?: string;
    code?: string;
    subtitle?: string;
    persona?: any;
  };
}

interface BackendTraceEventDTO {
  id: string;
  ts: string;
  rawTs: number;
  source: {
    id: string;
    kind: 'agent' | 'system' | 'runtime' | 'tool';
    displayName: string;
    accentColor?: string;
  };
  kind: string;
  detail: string;
  dur?: string;
  jobId?: string;
  taskId?: string;
  metadata?: Record<string, any>;
}

export class HttpHermesApi implements HermesApi {
  private baseUrl: string;
  private lastEventId: string | null = null;
  private activeEventSource: EventSource | null = null;

  constructor(baseUrl = 'http://localhost:8000') {
    // Strip trailing slash if present
    this.baseUrl = baseUrl.replace(/\/+$/, '');
  }

  /**
   * Single entry point for HTTP requests. A network failure is reported as HermesUnreachableError and
   * recorded for the connection banner; any HTTP response, whatever its status, counts as contact.
   */
  private async request(url: string, init?: RequestInit): Promise<Response> {
    let res: Response;
    try {
      res = init ? await fetch(url, init) : await fetch(url);
    } catch {
      recordUnreachable(this.baseUrl);
      throw new HermesUnreachableError(this.baseUrl);
    }
    recordContact();
    return res;
  }

  async getHealth(): Promise<HealthStatus> {
    const res = await this.request(`${this.baseUrl}/health`);
    if (!res.ok) {
      throw new Error(`Hermes /health returned HTTP ${res.status}: ${res.statusText}`);
    }
    return res.json();
  }

  async getAgents(): Promise<AgentSummary[]> {
    const res = await this.request(`${this.baseUrl}/agents`);
    if (!res.ok) {
      throw new Error(`Hermes /agents returned HTTP ${res.status}: ${res.statusText}`);
    }
    const data: BackendAgentDTO[] = await res.json();

    return data.map((dto) => {
      const actor = resolveActorPresentation(dto.id);
      
      return {
        id: dto.id,
        displayName: dto.displayName || actor.displayName,
        provider: dto.provider || 'Hermes Agent',
        model: dto.model || 'unknown',
        role: dto.role || 'Specialized Operative',
        capabilities: dto.capabilities || [],
        status: (dto.status?.toUpperCase() as any) || 'IDLE',
        phase: (dto.phase as any) || undefined,
        currentTask: dto.currentTask,
        activeTool: dto.activeTool,
        persona: dto.persona || dto.presentation?.persona,
        presentation: {
          displayName: dto.presentation?.displayName || dto.displayName || actor.displayName,
          accentColor: actorAccent(dto.id, dto.presentation?.accentColor || actor.accentColor),
          avatarUrl: dto.presentation?.avatarUrl || `/agents/${dto.id}.webp`,
          characterCardUrl: dto.presentation?.characterCardUrl || (['gemini', 'claude', 'codex'].includes(dto.id) ? `/agents/${dto.id}-card.webp` : undefined),
          sigil: dto.presentation?.sigil || dto.id.toUpperCase().slice(0, 4),
          code: dto.presentation?.code || dto.id.toUpperCase().slice(0, 4),
          subtitle: dto.presentation?.subtitle || dto.persona?.visual?.subtitle || dto.persona?.summary,
          persona: dto.persona || dto.presentation?.persona
        }
      };
    });
  }

  async getAgent(id: AgentId): Promise<AgentDetail | null> {
    const agents = await this.getAgents();
    const found = agents.find((a) => a.id.toLowerCase() === id.toLowerCase());
    if (!found) {
      return null;
    }

    // GET /agents carries identity and status only. Token, context, activity, run and quota
    // values are not fetched here, so they stay unknown rather than zero or a placeholder percentage.
    return {
      ...found,
      input: UNKNOWN,
      output: UNKNOWN,
      cached: UNKNOWN,
      remaining: UNKNOWN,
      inPct: UNKNOWN,
      outPct: UNKNOWN,
      cachePct: UNKNOWN,
      activity: [],
      metrics: [
        { label: 'STATUS', value: found.status }
      ],
      runs: [],
      allowance: [],
      capacity: UNKNOWN,
      reset: UNKNOWN,
      resetNote: 'Hermes GET /agents does not report provider capacity or reset windows.'
    };
  }

  // --------------------------------------------------------------------------
  // Real Job & Queue endpoints (Phase 4)
  // --------------------------------------------------------------------------

  async getJobs(status?: string): Promise<Job[]> {
    const params = new URLSearchParams();
    if (status) params.set('status', status);

    const res = await this.request(`${this.baseUrl}/jobs?${params.toString()}`);
    if (!res.ok) {
      throw new Error(`Hermes /jobs returned HTTP ${res.status}: ${res.statusText}`);
    }
    const data: any[] = await res.json();

    return data.map(mapJobSummary);
  }

  /** Recoverable jobs are read-only here: discovery only, no resume or cancel. */
  async getRecoverableJobs(): Promise<Job[]> {
    const res = await this.request(`${this.baseUrl}/jobs/recoverable`);
    if (!res.ok) {
      throw new Error(`Hermes /jobs/recoverable returned HTTP ${res.status}: ${res.statusText}`);
    }
    const data: any[] = await res.json();
    return data.map(mapJobSummary);
  }

  async getJob(id: string): Promise<JobDetail | null> {
    const res = await this.request(`${this.baseUrl}/jobs/${encodeURIComponent(id)}`);
    if (!res.ok) {
      if (res.status === 404) return null;
      throw new Error(`Hermes /jobs/${id} returned HTTP ${res.status}: ${res.statusText}`);
    }
    const data = await res.json();

    const phases = data.phases || [];
    const executionGraph: PipelineStep[] = phases.map((p: any) => {
      const actor = p.agentId ? resolveActorPresentation(p.agentId) : null;
      const rawStatus = typeof p.status === 'string' ? p.status : UNKNOWN;

      return {
        id: p.id || `phase-${p.order}`,
        jobId: data.id,
        phase: p.name,
        agentId: p.agentId,
        agentName: actor?.displayName || p.agentId,
        task: p.name,
        meta: p.commitSha ? p.commitSha.slice(0, 7) : (p.status === 'SUCCEEDED' ? 'completed' : rawStatus.toLowerCase()),
        state: mapPhaseState(p.status),
        note: p.role || (p.status === 'SUPERSEDED' ? 'superseded' : undefined)
      };
    });

    return {
      id: data.id,
      sprintId: data.sprintId,
      title: data.title,
      repository: data.repository,
      branch: data.branch,
      priority: data.priority || undefined,
      status: data.status,
      currentPhase: data.currentPhase,
      assignedAgentIds: data.assignedAgentIds || [],
      createdAt: data.createdAt,
      startedAt: data.startedAt,
      completedAt: data.completedAt,
      progress: data.progress,
      phases,
      tasks: data.tasks || [],
      observations: data.observations || [],
      blockedReason: data.blockedReason ?? null,
      repairCount: data.repairCount || 0,
      replanCount: data.replanCount || 0,
      verification: data.verification ?? null,
      executionGraph,
      changedFiles: [],
      retryHistory: data.retryHistory || [],
      retriesUsed: 0,
      maxRetries: 3,
      tokenBreakdown: [],
      artifacts: data.artifacts || [],
      errors: data.errors || []
    };
  }

  /** Steps of the job that is active right now. Empty when none is active; a historical job is never shown here. */
  async getPipeline(): Promise<PipelineStep[]> {
    const jobs = await this.getJobs();
    const activeJob = jobs.find((j) => ACTIVE_JOB_STATUSES.includes(j.status));
    if (!activeJob) {
      return [];
    }
    const detail = await this.getJob(activeJob.id);
    return (detail?.executionGraph || []).map((s) => ({
      ...s,
      jobId: activeJob.id
    }));
  }

  /**
   * Counts derived from the job list only. Errors propagate so the UI can show them instead of zeros.
   * Token, spend and budget values are not reported by Hermes in this milestone, so they stay unknown.
   */
  async getTelemetry(): Promise<OverviewTelemetry> {
    const jobs = await this.getJobs();
    const countOf = (...statuses: string[]) => jobs.filter((j) => statuses.includes(j.status)).length;

    // A failed job without a completion time cannot be placed in the 24h window, so the count is unknown.
    const cutoff = Date.now() - DAY_MS;
    let failed24hCount: number | null = 0;
    for (const j of jobs.filter((job) => job.status === 'FAILED')) {
      const endedAt = j.completedAt ? Date.parse(j.completedAt) : NaN;
      if (Number.isNaN(endedAt)) {
        failed24hCount = null;
        break;
      }
      if (endedAt >= cutoff) {
        failed24hCount = (failed24hCount ?? 0) + 1;
      }
    }

    return {
      runningJobsCount: countOf(...ACTIVE_JOB_STATUSES),
      queuedJobsCount: countOf('QUEUED', 'CLAIMED'),
      blockedJobsCount: countOf('BLOCKED'),
      failed24hCount,
      sampleSize: jobs.length,
      tokensToday: UNKNOWN,
      estSpendToday: UNKNOWN,
      sprintBudgetUsedPct: null
    };
  }

  async getTraceEvents(limit = 100, after?: string): Promise<TraceEvent[]> {
    const params = new URLSearchParams();
    if (limit) params.set('limit', String(limit));
    if (after) params.set('after', after);

    const res = await this.request(`${this.baseUrl}/events?${params.toString()}`);
    if (!res.ok) {
      throw new Error(`Hermes /events returned HTTP ${res.status}: ${res.statusText}`);
    }
    const data: BackendTraceEventDTO[] = await res.json();

    return data.map((e) => {
      const event = mapEvent(e);
      if (event.id) this.lastEventId = event.id;
      return event;
    });
  }

  subscribeEvents(
    handler: (event: TraceEvent) => void,
    onError?: (err: Error) => void,
    initialCursor?: string
  ): EventSubscription {
    if (this.activeEventSource) {
      this.activeEventSource.close();
      this.activeEventSource = null;
    }

    const cursor = initialCursor || this.lastEventId;
    const url = new URL(`${this.baseUrl}/events/stream`);
    if (cursor) {
      url.searchParams.set('after', cursor);
    }

    const eventSource = new EventSource(url.toString());
    this.activeEventSource = eventSource;

    const parseAndEmit = (rawEvent: MessageEvent) => {
      try {
        const event = mapEvent(JSON.parse(rawEvent.data));
        if (event.id) this.lastEventId = event.id;
        handler(event);
      } catch (err) {
        console.error('[HttpHermesApi] Failed to parse SSE event:', err, rawEvent.data);
      }
    };

    eventSource.addEventListener('trace', parseAndEmit);
    eventSource.onmessage = parseAndEmit;

    eventSource.onerror = (evt) => {
      console.warn('[HttpHermesApi] SSE connection warning / disconnect:', evt);
      onError?.(new Error('SSE connection disconnected from Hermes Runtime API'));
    };

    return {
      unsubscribe: () => {
        eventSource.removeEventListener('trace', parseAndEmit);
        eventSource.close();
        if (this.activeEventSource === eventSource) {
          this.activeEventSource = null;
        }
      }
    };
  }

  // --------------------------------------------------------------------------
  // D-009 Execution snapshot (GET /execution). Initial state; events are applied on top.
  // --------------------------------------------------------------------------

  async getExecutionSnapshot(): Promise<ExecutionSnapshot> {
    const res = await this.request(`${this.baseUrl}/execution`);
    if (!res.ok) {
      throw new Error(`Hermes /execution returned HTTP ${res.status}: ${res.statusText}`);
    }
    const data: any = await res.json();

    return {
      backends: (data.backends || []).map((b: any) => ({
        name: b.name,
        available: Boolean(b.available),
        detail: b.detail ?? ''
      })),
      resources: (data.resources || []).map((r: any) => ({
        backend: r.backend,
        kind: r.kind,
        id: r.id,
        label: r.label,
        state: r.state,
        jobId: r.jobId ?? null,
        taskId: r.taskId ?? null,
        executionId: r.executionId ?? null,
        since: r.since,
        expiresAt: r.expiresAt ?? null,
        details: r.details ?? {}
      })),
      openrig: data.openrig
        ? {
            daemon: data.openrig.daemon ?? 'unknown',
            ledger: {
              owners: data.openrig.ledger?.owners ?? 0,
              rigIds: data.openrig.ledger?.rigIds ?? []
            }
          }
        : null,
      // The cutoff for replayed events; dropping it would disable the reducer's snapshot cutoff.
      ...(typeof data.takenAt === 'number' ? { takenAt: data.takenAt } : {})
    };
  }

  // --------------------------------------------------------------------------
  // Quota & Projections: no real source is wired yet, so these return nothing rather than a measurement
  // --------------------------------------------------------------------------

  /** No projection source exists in Hermes yet, so there are no projected rows in HTTP mode. */
  async getProjections(): Promise<ProjectionItem[]> {
    return [];
  }

  async getSettings(): Promise<{ runtime: SettingItem[]; policy: SettingItem[] }> {
    return {
      runtime: [
        { label: 'Hermes Runtime API', value: this.baseUrl, color: 'var(--lys-status-success)' },
        { label: 'Event Bus Transport', value: 'SSE / Server-Sent Events', color: 'var(--lys-accent-gold)' }
      ],
      // The Hermes API does not expose its execution or merge policy, so none is claimed here.
      policy: [
        { label: 'Policy', value: 'Not exposed by the Hermes API', color: 'var(--lys-text-muted)' }
      ]
    };
  }

  async sendOperatorCommand(targetActorId: string, _command: string): Promise<{ success: boolean; response: string }> {
    return {
      success: false,
      response: `[Hermes / ${targetActorId}] Command execution is not available in real Hermes API mode yet.`
    };
  }

  async triggerJobAction(jobId: string, action: 'retry' | 'pause' | 'cancel' | 'promote'): Promise<boolean> {
    if (action === 'cancel') {
      try {
        const res = await this.request(`${this.baseUrl}/jobs/${encodeURIComponent(jobId)}/cancel`, {
          method: 'POST'
        });
        return res.ok;
      } catch (err) {
        console.error('[HttpHermesApi] Failed to cancel job:', err);
        return false;
      }
    }

    console.warn(`[HttpHermesApi] Action '${action}' on job ${jobId} is not available in real Hermes API mode yet.`);
    return false;
  }
  // --------------------------------------------------------------------------
  // Phase 5 Operational Messaging & Threads
  // --------------------------------------------------------------------------

  async getThreads(jobId?: string, participant?: string, limit?: number): Promise<Thread[]> {
    const params = new URLSearchParams();
    if (jobId) params.set("jobId", jobId);
    if (participant) params.set("participant", participant);
    if (limit) params.set("limit", String(limit));

    const res = await this.request(`${this.baseUrl}/threads?${params.toString()}`);
    if (!res.ok) {
      throw new Error(`Hermes /threads returned HTTP ${res.status}: ${res.statusText}`);
    }
    const data: any[] = await res.json();
    return data.map((t) => ({
      id: t.id,
      jobId: t.jobId,
      title: t.title,
      participants: (t.participants || []).map((p: any) => ({
        id: p.id,
        kind: p.kind,
        displayName: p.displayName || resolveActorPresentation(p.id).displayName,
        accentColor: actorAccent(p.id, p.accentColor)
      })),
      createdAt: t.createdAt,
      updatedAt: t.updatedAt
    }));
  }

  async getThread(threadId: string): Promise<Thread | null> {
    const res = await this.request(`${this.baseUrl}/threads/${encodeURIComponent(threadId)}`);
    if (!res.ok) {
      if (res.status === 404) return null;
      throw new Error(`Hermes /threads/${threadId} returned HTTP ${res.status}: ${res.statusText}`);
    }
    const t = await res.json();
    return {
      id: t.id,
      jobId: t.jobId,
      title: t.title,
      participants: (t.participants || []).map((p: any) => ({
        id: p.id,
        kind: p.kind,
        displayName: p.displayName || resolveActorPresentation(p.id).displayName,
        accentColor: actorAccent(p.id, p.accentColor)
      })),
      createdAt: t.createdAt,
      updatedAt: t.updatedAt
    };
  }

  async getMessages(threadId: string, limit?: number, after?: string, conversationId?: string): Promise<Message[]> {
    const params = new URLSearchParams();
    if (limit) params.set("limit", String(limit));
    if (after) params.set("after", after);
    if (conversationId) params.set("conversationId", conversationId);

    const res = await this.request(`${this.baseUrl}/threads/${encodeURIComponent(threadId)}/messages?${params.toString()}`);
    if (!res.ok) {
      // A 404 means the thread does not exist. That is an error to show, not an empty conversation.
      throw new Error(`Hermes /threads/${threadId}/messages returned HTTP ${res.status}: ${res.statusText}`);
    }
    const data: any[] = await res.json();
    return data.map((m) => {
      const fromActor = resolveActorPresentation(m.from?.id || "unknown");
      return {
        id: m.id,
        threadId: m.threadId,
        from: {
          id: m.from?.id,
          kind: m.from?.kind || "agent",
          displayName: m.from?.displayName || fromActor.displayName,
          accentColor: actorAccent(m.from?.id ?? fromActor.id, m.from?.accentColor || fromActor.accentColor),
          avatarUrl: m.from?.avatarUrl || fromActor.avatarUrl,
          subtitle: m.from?.subtitle || fromActor.subtitle
        },
        to: (m.to || []).map((to: any) => {
          const toActor = resolveActorPresentation(to.id || "unknown");
          return {
            id: to.id,
            kind: to.kind || "agent",
            displayName: to.displayName || toActor.displayName,
            accentColor: actorAccent(to.id, to.accentColor || toActor.accentColor),
            avatarUrl: to.avatarUrl || toActor.avatarUrl,
            subtitle: to.subtitle || toActor.subtitle
          };
        }),
        kind: m.kind,
        text: m.text,
        intent: m.intent,
        conversationId: m.conversationId,
        replyTo: m.replyTo,
        correlationId: m.correlationId,
        jobId: m.jobId,
        phaseId: m.phaseId,
        artifactRefs: m.artifactRefs || [],
        metadata: m.metadata || {},
        createdAt: m.createdAt
      };
    });
  }

  async getAgentInbox(agentId: string, state?: string, limit?: number, conversationId?: string): Promise<MailboxEntry[]> {
    const params = new URLSearchParams();
    if (state) params.set("state", state);
    if (limit) params.set("limit", String(limit));
    if (conversationId) params.set("conversationId", conversationId);

    const res = await this.request(`${this.baseUrl}/agents/${encodeURIComponent(agentId)}/inbox?${params.toString()}`);
    if (!res.ok) {
      throw new Error(`Hermes /agents/${agentId}/inbox returned HTTP ${res.status}: ${res.statusText}`);
    }
    const data: any[] = await res.json();
    return data.map((e) => ({
      messageId: e.messageId,
      recipientId: e.recipientId,
      state: e.state,
      receivedAt: e.receivedAt,
      acknowledgedAt: e.acknowledgedAt,
      message: e.message
    }));
  }

  // --------------------------------------------------------------------------
  // M2 real data: capacity, job telemetry, tasks, runs, observations, job events
  // --------------------------------------------------------------------------

  private async getJson(path: string, label: string): Promise<any> {
    const res = await this.request(`${this.baseUrl}${path}`);
    if (!res.ok) {
      throw new Error(`Hermes ${label} returned HTTP ${res.status}: ${res.statusText}`);
    }
    return res.json();
  }

  async getCapacityTelemetry(): Promise<CapacityTelemetry> {
    return mapCapacityTelemetry(await this.getJson('/capacity/telemetry', '/capacity/telemetry'));
  }

  async getJobTelemetry(jobId: string): Promise<JobTokenTelemetry> {
    const id = encodeURIComponent(jobId);
    return mapJobTokenTelemetry(await this.getJson(`/jobs/${id}/telemetry`, `/jobs/${jobId}/telemetry`), jobId);
  }

  async getJobTasks(jobId: string): Promise<TaskNode[]> {
    const id = encodeURIComponent(jobId);
    const data: any[] = await this.getJson(`/jobs/${id}/tasks`, `/jobs/${jobId}/tasks`);
    return data.map(mapTaskNode);
  }

  async getJobRuns(jobId: string): Promise<AgentRun[]> {
    const id = encodeURIComponent(jobId);
    const data: any[] = await this.getJson(`/jobs/${id}/runs`, `/jobs/${jobId}/runs`);
    return data.map(mapAgentRun);
  }

  async getJobObservations(jobId: string): Promise<JobObservation[]> {
    const id = encodeURIComponent(jobId);
    const data: any[] = await this.getJson(`/jobs/${id}/observations`, `/jobs/${jobId}/observations`);
    return data.map(mapObservation);
  }

  /** Durable job history, normalised from the stored envelope. Live SSE events are merged by the store. */
  async getJobEvents(jobId: string, limit = 500): Promise<TraceEvent[]> {
    const id = encodeURIComponent(jobId);
    const data: any[] = await this.getJson(
      `/jobs/${id}/events?limit=${limit}`,
      `/jobs/${jobId}/events`
    );
    return data.map(mapEvent);
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
    const res = await this.request(`${this.baseUrl}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        threadId,
        text,
        to,
        kind: kind || "operator",
        intent,
        conversationId,
        replyTo,
        correlationId
      })
    });
    if (!res.ok) {
      throw new Error(`Hermes POST /messages returned HTTP ${res.status}: ${res.statusText}`);
    }
    const m = await res.json();
    const fromActor = resolveActorPresentation(m.from?.id || "operator");
    return {
      id: m.id,
      threadId: m.threadId,
      from: {
        id: m.from?.id,
        kind: m.from?.kind || "operator",
        displayName: m.from?.displayName || fromActor.displayName,
        accentColor: actorAccent(m.from?.id ?? fromActor.id, m.from?.accentColor || fromActor.accentColor)
      },
      to: (m.to || []).map((to: any) => ({
        id: to.id,
        kind: to.kind || "agent",
        displayName: to.displayName || resolveActorPresentation(to.id).displayName,
        accentColor: actorAccent(to.id, to.accentColor || resolveActorPresentation(to.id).accentColor)
      })),
      kind: m.kind,
      text: m.text,
      intent: m.intent,
      conversationId: m.conversationId,
      replyTo: m.replyTo,
      correlationId: m.correlationId,
      jobId: m.jobId,
      phaseId: m.phaseId,
      artifactRefs: m.artifactRefs || [],
      metadata: m.metadata || {},
      createdAt: m.createdAt
    };
  }
}

