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
} from './types';

export interface EventSubscription {
  unsubscribe(): void;
}

export interface LysStackApi {
  getHealth(): Promise<HealthStatus>;
  getAgents(): Promise<AgentSummary[]>;
  getAgent(id: AgentId): Promise<AgentDetail | null>;
  getJobs(): Promise<Job[]>;
  getJob(id: string): Promise<JobDetail | null>;
  getPipeline(): Promise<PipelineStep[]>;
  getTelemetry(): Promise<OverviewTelemetry>;
  getProviderQuotas(): Promise<ProviderQuota[]>;
  getProjections(): Promise<ProjectionItem[]>;
  getSettings(): Promise<{ runtime: SettingItem[]; policy: SettingItem[] }>;
  getTraceEvents(limit?: number, after?: string): Promise<TraceEvent[]>;
  subscribeEvents(
    handler: (event: TraceEvent) => void,
    onError?: (err: Error) => void,
    initialCursor?: string
  ): EventSubscription;
  sendOperatorCommand(targetActorId: string, command: string): Promise<{ success: boolean; response: string }>;
  triggerJobAction(jobId: string, action: 'retry' | 'pause' | 'cancel' | 'promote'): Promise<boolean>;
}
