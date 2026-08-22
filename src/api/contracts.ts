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
  HealthStatus,
  Thread,
  Message,
  MailboxEntry
} from './types';

export interface EventSubscription {
  unsubscribe(): void;
}

export interface LysStackApi {
  getHealth(): Promise<HealthStatus>;
  getAgents(): Promise<AgentSummary[]>;
  getAgent(id: AgentId): Promise<AgentDetail | null>;
  getJobs(status?: string): Promise<Job[]>;
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

  // Phase 5 / Phase 6 Operational Messaging, A2A & Threads
  getThreads(jobId?: string, participant?: string, limit?: number): Promise<Thread[]>;
  getThread(threadId: string): Promise<Thread | null>;
  getMessages(threadId: string, limit?: number, after?: string, conversationId?: string): Promise<Message[]>;
  getAgentInbox(agentId: string, state?: string, limit?: number, conversationId?: string): Promise<MailboxEntry[]>;
  sendMessage(
    threadId: string,
    text: string,
    to?: string[],
    kind?: string,
    intent?: string,
    conversationId?: string,
    replyTo?: string,
    correlationId?: string
  ): Promise<Message>;
}
