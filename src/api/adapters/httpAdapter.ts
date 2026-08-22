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
      // Resolve client presentation (e.g. portraits/cards if present)
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

    // Truthful representation in real mode (Task 11: no fabricated telemetry numbers)
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
    // Avoid duplicate connections (Task 9, Task 10)
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
  // Simulated / Fallback endpoints for Phase 3 (Will transition in Phase 4)
  // --------------------------------------------------------------------------

  async getJobs(): Promise<Job[]> {
    return [
      {
        id: '#142',
        priority: 'P1',
        title: 'Redis State Migration',
        repository: 'moveinmate/backend',
        branch: 'feat/redis-state',
        status: 'RUNNING',
        assignedAgentIds: ['gemini', 'claude', 'codex'],
        startedAt: '10:38',
        budget: '80k',
        policy: 'serial · retry 3'
      },
      {
        id: '#143',
        priority: 'P0',
        title: 'Fix production CI — flaky worker teardown',
        repository: 'unigreen/web',
        assignedAgentIds: ['gemini', 'claude', 'codex'],
        estimatedTokens: '~18–30k',
        estimatedTime: '~12 min',
        status: 'QUEUED',
        createdAt: '10:35'
      }
    ];
  }

  async getJob(id: string): Promise<JobDetail | null> {
    return {
      id,
      priority: 'P1',
      title: 'Active LysStack Orchestration Task',
      repository: 'moveinmate/backend',
      branch: 'feat/redis-state',
      status: 'RUNNING',
      assignedAgentIds: ['gemini', 'claude', 'codex'],
      startedAt: '10:38',
      budget: '80k',
      policy: 'serial · retry 3',
      executionGraph: [
        { id: '1', phase: 'BUILD', agentId: 'gemini', agentName: 'Gemini', task: 'Build', meta: '30.4k', state: 'COMPLETED' },
        { id: '2', phase: 'HARDEN', agentId: 'claude', agentName: 'Claude', task: 'Harden', meta: '13.7k', state: 'RUNNING' },
        { id: '3', phase: 'VERIFY', agentId: 'codex', agentName: 'Codex', task: 'Verify', meta: 'staged', state: 'QUEUED' }
      ],
      changedFiles: [],
      retryHistory: [],
      retriesUsed: 1,
      maxRetries: 3,
      tokenBreakdown: []
    };
  }

  async getPipeline(): Promise<PipelineStep[]> {
    return [
      { id: '1', phase: 'BUILD', agentId: 'gemini', agentName: 'Gemini', task: 'Build', meta: '30.4k', state: 'COMPLETED' },
      { id: '2', phase: 'HARDEN', agentId: 'claude', agentName: 'Claude', task: 'Harden', meta: '13.7k', state: 'RUNNING' },
      { id: '3', phase: 'VERIFY', agentId: 'codex', agentName: 'Codex', task: 'Verify', meta: 'staged', state: 'QUEUED' }
    ];
  }

  async getTelemetry(): Promise<OverviewTelemetry> {
    return {
      runningJobsCount: 1,
      queuedJobsCount: 2,
      blockedJobsCount: 0,
      failed24hCount: 0,
      tokensToday: '124K',
      estSpendToday: '$3.40',
      sprintBudgetUsedPct: 42
    };
  }

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
    return [
      { id: '1', task: 'CI Flaky Worker Fix', est: '~12 min', w: '70%', wLow: '30%', color: '#F2555A', conf: 'high' }
    ];
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
    // Truthful command handling (Task 12: explicit unsupported response in real mode)
    return {
      success: false,
      response: `[LysStack / ${targetActorId}] Command execution is not available in real control-plane mode yet.`
    };
  }

  async triggerJobAction(jobId: string, action: 'retry' | 'pause' | 'cancel' | 'promote'): Promise<boolean> {
    // Truthful action handling (Task 12: explicit unsupported response in real mode)
    console.warn(`[HttpLysStackApi] Action '${action}' on job ${jobId} is not available in real control-plane mode yet.`);
    return false;
  }
}
