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
  OverviewTelemetry
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
import { resolveActorPresentation } from '../actors';

function fmtTs(sec: number): string {
  const h = Math.floor(sec / 3600);
  const m = Math.floor(sec / 60) % 60;
  const s = Math.floor(sec % 60);
  const ms = Math.round((sec - Math.floor(sec)) * 1000);
  const pad = (n: number, w: number) => String(n).padStart(w, '0');
  return `${pad(h, 2)}:${pad(m, 2)}:${pad(s, 2)}.${pad(ms, 3)}`;
}

export class MockLysStackApi implements LysStackApi {
  private agents: Record<AgentId, AgentDetail> = { ...MOCK_AGENTS };
  private jobs: Job[] = [...MOCK_JOBS];
  private pipeline: PipelineStep[] = [...MOCK_PIPELINE];
  private simTick = 0;
  private lastSimTs = 10 * 3600 + 42 * 60 + 47.4;

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

  async getTraceEvents(limit = 20): Promise<TraceEvent[]> {
    const baseTs = 10 * 3600 + 42 * 60 + 16;
    const agentList = Object.values(this.agents);

    return RAW_SEED_EVENTS.slice(0, limit).map((e, idx) => ({
      id: `seed-${idx}`,
      ts: fmtTs(baseTs + e.t),
      rawTs: baseTs + e.t,
      source: resolveActorPresentation(e.a, agentList),
      kind: e.k,
      detail: e.d,
      dur: e.dur || '—',
      jobId: '#142'
    })).reverse();
  }

  subscribeEvents(handler: (event: TraceEvent) => void): EventSubscription {
    const agentList = Object.values(this.agents);

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
      }
    };
  }

  async sendOperatorCommand(targetActorId: string, command: string): Promise<{ success: boolean; response: string }> {
    return {
      success: true,
      response: `[LysStack / ${targetActorId}] Dispatched: "${command}". Processed by mock adapter.`
    };
  }

  async triggerJobAction(jobId: string, action: 'retry' | 'pause' | 'cancel' | 'promote'): Promise<boolean> {
    console.log(`[MockLysStackApi] Action '${action}' on job ${jobId}`);
    return true;
  }
}
