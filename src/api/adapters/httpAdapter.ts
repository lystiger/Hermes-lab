import { LysStackApi, EventSubscription } from '../contracts';
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
  HealthStatus
} from '../types';
import { resolveActorPresentation } from '../actors';

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
  presentation?: {
    displayName: string;
    accentColor?: string;
    avatarUrl?: string;
    characterCardUrl?: string;
    sigil?: string;
    code?: string;
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
  metadata?: Record<string, any>;
}

export class HttpLysStackApi implements LysStackApi {
  private baseUrl: string;
  private lastEventId: string | null = null;
  private activeEventSource: EventSource | null = null;

  constructor(baseUrl = 'http://localhost:8000') {
    // Strip trailing slash if present
    this.baseUrl = baseUrl.replace(/\/+$/, '');
  }

  async getHealth(): Promise<HealthStatus> {
    const res = await fetch(`${this.baseUrl}/health`);
    if (!res.ok) {
      throw new Error(`LysStack /health returned HTTP ${res.status}: ${res.statusText}`);
    }
    return res.json();
  }

  async getAgents(): Promise<AgentSummary[]> {
    const res = await fetch(`${this.baseUrl}/agents`);
    if (!res.ok) {
      throw new Error(`LysStack /agents returned HTTP ${res.status}: ${res.statusText}`);
    }
    const data: BackendAgentDTO[] = await res.json();

    return data.map((dto) => {
      const actor = resolveActorPresentation(dto.id);
      
      return {
        id: dto.id,
        displayName: dto.displayName || actor.displayName,
        provider: dto.provider || 'LysStack Agent',
        model: dto.model || 'unknown',
        role: dto.role || 'Specialized Operative',
        capabilities: dto.capabilities || ['execution'],
        status: (dto.status?.toUpperCase() as any) || 'IDLE',
        phase: (dto.phase as any) || undefined,
        currentTask: dto.currentTask,
        activeTool: dto.activeTool,
        presentation: {
          displayName: dto.presentation?.displayName || dto.displayName || actor.displayName,
          accentColor: dto.presentation?.accentColor || actor.accentColor,
          avatarUrl: dto.presentation?.avatarUrl || `/agents/${dto.id}.webp`,
          characterCardUrl: dto.presentation?.characterCardUrl || (['gemini', 'claude', 'codex'].includes(dto.id) ? `/agents/${dto.id}-card.webp` : undefined),
          sigil: dto.presentation?.sigil || dto.id.toUpperCase().slice(0, 4),
          code: dto.presentation?.code || dto.id.toUpperCase().slice(0, 4)
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

    return {
      ...found,
      input: '—',
      output: '—',
      cached: '—',
      remaining: '—',
      inPct: '0%',
      outPct: '0%',
      cachePct: '0%',
      activity: [],
      metrics: [
        { label: 'STATUS', value: found.status }
      ],
      runs: [],
      allowance: [
        { label: 'fleet quota', value: 'Unavailable', pct: '0%', tag: 'N/A' }
      ],
      capacity: 'Live capacity not exposed',
      reset: '—',
      resetNote: 'Detailed provider token telemetry will connect in Phase 4.'
    };
  }

  // --------------------------------------------------------------------------
  // Real Job & Queue endpoints (Phase 4)
  // --------------------------------------------------------------------------

  async getJobs(status?: string): Promise<Job[]> {
    const params = new URLSearchParams();
    if (status) params.set('status', status);

    const res = await fetch(`${this.baseUrl}/jobs?${params.toString()}`);
    if (!res.ok) {
      throw new Error(`LysStack /jobs returned HTTP ${res.status}: ${res.statusText}`);
    }
    const data: any[] = await res.json();

    return data.map((j) => ({
      id: j.id,
      sprintId: j.sprintId,
      title: j.title,
      repository: j.repository,
      branch: j.branch,
      priority: j.priority || 'P1',
      status: j.status,
      currentPhase: j.currentPhase,
      assignedAgentIds: j.assignedAgentIds || [],
      createdAt: j.createdAt,
      startedAt: j.startedAt,
      completedAt: j.completedAt,
      progress: j.progress,
      estimatedTokens: '—',
      estimatedTime: '—',
      budget: '—',
      policy: 'governed · serial'
    }));
  }

  async getJob(id: string): Promise<JobDetail | null> {
    const res = await fetch(`${this.baseUrl}/jobs/${encodeURIComponent(id)}`);
    if (!res.ok) {
      if (res.status === 404) return null;
      throw new Error(`LysStack /jobs/${id} returned HTTP ${res.status}: ${res.statusText}`);
    }
    const data = await res.json();

    const phases = data.phases || [];
    const executionGraph: PipelineStep[] = phases.map((p: any) => {
      const actor = p.agentId ? resolveActorPresentation(p.agentId) : null;
      let state: any = 'QUEUED';
      if (p.status === 'SUCCEEDED') state = 'COMPLETED';
      else if (p.status === 'RUNNING') state = 'RUNNING';
      else if (p.status === 'FAILED') state = 'BLOCKED';
      else if (p.status === 'CANCELLED') state = 'BLOCKED';

      return {
        id: p.id || `phase-${p.order}`,
        jobId: data.id,
        phase: p.name,
        agentId: p.agentId,
        agentName: actor?.displayName || p.agentId,
        task: p.name,
        meta: p.commitSha ? p.commitSha.slice(0, 7) : (p.status === 'SUCCEEDED' ? 'completed' : p.status.toLowerCase()),
        state,
        note: p.role
      };
    });

    return {
      id: data.id,
      sprintId: data.sprintId,
      title: data.title,
      repository: data.repository,
      branch: data.branch,
      priority: data.priority || 'P1',
      status: data.status,
      currentPhase: data.currentPhase,
      assignedAgentIds: data.assignedAgentIds || [],
      createdAt: data.createdAt,
      startedAt: data.startedAt,
      completedAt: data.completedAt,
      progress: data.progress,
      phases,
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

  async getPipeline(): Promise<PipelineStep[]> {
    try {
      const jobs = await this.getJobs();
      const activeJob = jobs.find((j) => j.status === 'RUNNING') || jobs[0];
      if (!activeJob) {
        return [];
      }
      const detail = await this.getJob(activeJob.id);
      return (detail?.executionGraph || []).map((s) => ({
        ...s,
        jobId: activeJob.id
      }));
    } catch {
      return [];
    }
  }

  async getTelemetry(): Promise<OverviewTelemetry> {
    try {
      const jobs = await this.getJobs();
      const runningJobsCount = jobs.filter((j) => j.status === 'RUNNING').length;
      const queuedJobsCount = jobs.filter((j) => ['QUEUED', 'PREPARING'].includes(j.status)).length;
      const blockedJobsCount = jobs.filter((j) => j.status === 'BLOCKED').length;
      const failed24hCount = jobs.filter((j) => j.status === 'FAILED').length;

      return {
        runningJobsCount,
        queuedJobsCount,
        blockedJobsCount,
        failed24hCount,
        tokensToday: '—',
        estSpendToday: '—',
        sprintBudgetUsedPct: 0
      };
    } catch {
      return {
        runningJobsCount: 0,
        queuedJobsCount: 0,
        blockedJobsCount: 0,
        failed24hCount: 0,
        tokensToday: '—',
        estSpendToday: '—',
        sprintBudgetUsedPct: 0
      };
    }
  }

  async getTraceEvents(limit = 100, after?: string): Promise<TraceEvent[]> {
    const params = new URLSearchParams();
    if (limit) params.set('limit', String(limit));
    if (after) params.set('after', after);

    const res = await fetch(`${this.baseUrl}/events?${params.toString()}`);
    if (!res.ok) {
      throw new Error(`LysStack /events returned HTTP ${res.status}: ${res.statusText}`);
    }
    const data: BackendTraceEventDTO[] = await res.json();

    return data.map((e) => {
      if (e.id) this.lastEventId = e.id;
      return {
        id: e.id,
        ts: e.ts,
        rawTs: e.rawTs,
        source: {
          id: e.source.id,
          kind: e.source.kind,
          displayName: e.source.displayName,
          accentColor: e.source.accentColor || resolveActorPresentation(e.source.id).accentColor
        },
        kind: e.kind,
        detail: e.detail,
        dur: e.dur || '—',
        jobId: e.jobId,
        metadata: e.metadata
      };
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
        const dto: BackendTraceEventDTO = JSON.parse(rawEvent.data);
        if (dto.id) this.lastEventId = dto.id;

        const event: TraceEvent = {
          id: dto.id,
          ts: dto.ts,
          rawTs: dto.rawTs,
          source: {
            id: dto.source.id,
            kind: dto.source.kind,
            displayName: dto.source.displayName,
            accentColor: dto.source.accentColor || resolveActorPresentation(dto.source.id).accentColor
          },
          kind: dto.kind,
          detail: dto.detail,
          dur: dto.dur || '—',
          jobId: dto.jobId,
          metadata: dto.metadata
        };

        handler(event);
      } catch (err) {
        console.error('[HttpLysStackApi] Failed to parse SSE event:', err, rawEvent.data);
      }
    };

    eventSource.addEventListener('trace', parseAndEmit);
    eventSource.onmessage = parseAndEmit;

    eventSource.onerror = (evt) => {
      console.warn('[HttpLysStackApi] SSE connection warning / disconnect:', evt);
      onError?.(new Error('SSE connection disconnected from LysStack control plane'));
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
  // Quota & Projections (Phase 4 simulated until provider accounting)
  // --------------------------------------------------------------------------

  async getProviderQuotas(): Promise<ProviderQuota[]> {
    return [
      {
        id: 'google',
        name: 'Google AI Studio',
        color: '#5B8CFF',
        pct: '56%',
        tag: 'EXACT',
        window: 'daily',
        left: '666 req left',
        capacity: '1,500 req/day',
        reset: 'daily 00:00 UTC',
        resetTag: 'EXACT',
        conf: 'exact',
        basis: 'AI Studio reported quota',
        opacity: '1'
      }
    ];
  }

  async getProjections(): Promise<ProjectionItem[]> {
    return [];
  }

  async getSettings(): Promise<{ runtime: SettingItem[]; policy: SettingItem[] }> {
    return {
      runtime: [
        { label: 'LysStack Control API', value: this.baseUrl, color: '#3FB950' },
        { label: 'Event Bus Transport', value: 'SSE / Server-Sent Events', color: '#CBA35C' }
      ],
      policy: [
        { label: 'Execution Mode', value: 'Governed Hermes Runtime', color: '#E6E9ED' },
        { label: 'Auto-Merge Policy', value: 'Human Review Required (Strict)', color: '#E3A008' }
      ]
    };
  }

  async sendOperatorCommand(targetActorId: string, _command: string): Promise<{ success: boolean; response: string }> {
    return {
      success: false,
      response: `[LysStack / ${targetActorId}] Command execution is not available in real control-plane mode yet.`
    };
  }

  async triggerJobAction(jobId: string, action: 'retry' | 'pause' | 'cancel' | 'promote'): Promise<boolean> {
    if (action === 'cancel') {
      try {
        const res = await fetch(`${this.baseUrl}/jobs/${encodeURIComponent(jobId)}/cancel`, {
          method: 'POST'
        });
        return res.ok;
      } catch (err) {
        console.error('[HttpLysStackApi] Failed to cancel job:', err);
        return false;
      }
    }

    console.warn(`[HttpLysStackApi] Action '${action}' on job ${jobId} is not available in real control-plane mode yet.`);
    return false;
  }
}
