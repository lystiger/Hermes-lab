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
  CapacityTelemetry,
  AgentLimitsReport,
  JobTokenTelemetry,
  RunReview,
  TaskNode,
  AgentRun,
  JobObservation,
  AgentModelsMap,
  SetAgentModelResponse
} from './types';

export interface EventSubscription {
  unsubscribe(): void;
}

export interface HermesApi {
  /** Wait for outstanding HTTP requests; adapters without HTTP traffic need no barrier. */
  waitForIdle?(signal?: AbortSignal): Promise<void>;
  getHealth(): Promise<HealthStatus>;
  getAgents(): Promise<AgentSummary[]>;
  getAgent(id: AgentId): Promise<AgentDetail | null>;
  getJobs(status?: string): Promise<Job[]>;
  getJob(id: string): Promise<JobDetail | null>;
  getPipeline(): Promise<PipelineStep[]>;
  getTelemetry(): Promise<OverviewTelemetry>;
  getCapacityTelemetry(): Promise<CapacityTelemetry>;
  getAgentLimits(): Promise<AgentLimitsReport>;
  getJobTelemetry(jobId: string): Promise<JobTokenTelemetry>;
  /** Finished goal-planned runs for human review, newest first. */
  getReviews(): Promise<RunReview[]>;
  getJobTasks(jobId: string): Promise<TaskNode[]>;
  getJobRuns(jobId: string): Promise<AgentRun[]>;
  getJobObservations(jobId: string): Promise<JobObservation[]>;
  getJobEvents(jobId: string, limit?: number): Promise<TraceEvent[]>;
  getRecoverableJobs(): Promise<Job[]>;
  getProjections(): Promise<ProjectionItem[]>;
  getSettings(): Promise<{ runtime: SettingItem[]; policy: SettingItem[] }>;
  getExecutionSnapshot(): Promise<ExecutionSnapshot>;
  getTraceEvents(limit?: number, after?: string): Promise<TraceEvent[]>;
  subscribeEvents(
    handler: (event: TraceEvent) => void,
    onError?: (err: Error) => void,
    initialCursor?: string
  ): EventSubscription;
  sendOperatorCommand(targetActorId: string, command: string): Promise<{ success: boolean; response: string }>;
  triggerJobAction(jobId: string, action: 'retry' | 'pause' | 'cancel' | 'promote'): Promise<boolean>;

  // M8 Agent Model Registry
  getAgentModels(): Promise<AgentModelsMap>;
  setAgentModel(agentId: string, model: string, effort?: string | null): Promise<SetAgentModelResponse>;

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
