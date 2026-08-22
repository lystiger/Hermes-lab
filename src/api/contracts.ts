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
} from './types';

export interface LysStackApi {
  getAgents(): Promise<AgentSummary[]>;
  getAgent(id: AgentId): Promise<AgentDetail | null>;
  getJobs(): Promise<Job[]>;
  getJob(id: string): Promise<JobDetail | null>;
  getPipeline(): Promise<PipelineStep[]>;
  getTelemetry(): Promise<OverviewTelemetry>;
  getProviderQuotas(): Promise<ProviderQuota[]>;
  getProjections(): Promise<ProjectionItem[]>;
  getSettings(): Promise<{ runtime: SettingItem[]; policy: SettingItem[] }>;
  getTraceEvents(limit?: number): Promise<TraceEvent[]>;
  sendOperatorCommand(targetActorId: string, command: string): Promise<{ success: boolean; response: string }>;
  triggerJobAction(jobId: string, action: 'retry' | 'pause' | 'cancel' | 'promote'): Promise<boolean>;
}
