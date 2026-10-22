// Generic Agent Identity (No closed unions)
export type AgentId = string;

export type AgentStatus = 'RUNNING' | 'WAITING' | 'IDLE' | 'OFFLINE' | 'BUSY' | 'ERROR';

export type Priority = 'P0' | 'P1' | 'P2' | 'P3';

export type JobStatus =
  | 'CREATED'
  | 'EXECUTING'
  | 'WAITING_FOR_CAPACITY'
  | 'QUEUED'
  | 'PLANNING'
  | 'PREPARING'
  | 'RUNNING'
  | 'VERIFYING'
  | 'REPAIRING'
  | 'BLOCKED'
  | 'FAILED'
  | 'COMPLETED'
  | 'CANCELLED'
  | 'CLAIMED';

export type PhaseStatus =
  | 'PENDING'
  | 'READY'
  | 'PREPARING'
  | 'RUNNING'
  | 'SUCCEEDED'
  | 'FAILED'
  | 'SKIPPED'
  | 'CANCELLED'
  | 'SUPERSEDED'
  | 'BLOCKED';

// Terminal failure/cancel/skip states are kept distinct from BLOCKED; UNKNOWN is a raw status we do not map.
export type PipelineStepState =
  | 'COMPLETED'
  | 'RUNNING'
  | 'QUEUED'
  | 'CLAIMED'
  | 'BLOCKED'
  | 'FAILED'
  | 'CANCELLED'
  | 'SKIPPED'
  | 'UNKNOWN'
  | 'IDLE';

export type PhaseName = string;

export type ActorKind = 'agent' | 'system' | 'runtime' | 'tool' | 'operator';

export type ConnectionStatus = 'CONNECTING' | 'CONNECTED' | 'DEGRADED' | 'DISCONNECTED';

export interface HealthStatus {
  status: string;
  service: string;
  version: string;
  uptimeSeconds: number;
  timestamp: string;
}

export interface ActorRef {
  id: string;
  kind: ActorKind | string;
  displayName: string;
  accentColor?: string;
  avatarUrl?: string;
  subtitle?: string;
}

export interface PersonaVisual {
  avatar?: string;
  subtitle?: string;
  accentColor?: string;
  badgeText?: string;
}

export interface PersonaProfile {
  name: string;
  summary: string;
  traits: string[];
  speakingStyle: string[];
  behavioralRules: string[];
  relationships?: Record<string, string>;
  systemPromptFragment?: string;
  visual?: PersonaVisual;
}

export interface AgentProfile {
  id: AgentId;
  displayName: string;
  provider?: string;
  model?: string;
  persona?: PersonaProfile;
  capabilities?: string[];
  metadata?: Record<string, any>;
}

export interface AgentPresentation {
  displayName: string;
  avatarUrl?: string;
  characterCardUrl?: string;
  accentColor?: string;
  animationProfile?: 'quick' | 'relaxed' | 'slow' | 'steady' | 'none';
  sigil?: string;
  code?: string;
  badge?: string;
  subtitle?: string;
  persona?: PersonaProfile;
}

export interface ActivityItem {
  op: 'READ' | 'WRITE' | 'RUN' | 'STAGE' | 'NOTE' | 'IDLE' | 'CUSTOM';
  path: string;
  meta: string;
}

export interface MetricItem {
  label: string;
  value: string;
  sub?: string;
  color?: string;
}

export interface RunHistoryItem {
  id: string;
  phase: PhaseName;
  task: string;
  tokens: string;
  dur: string;
  result: 'PASSED' | 'RUNNING' | 'FAILED' | 'RETRIED' | 'RATE LIMITED';
}

export interface AllowanceItem {
  label: string;
  value: string;
  pct: string;
  tag: 'EXACT' | 'EST' | 'N/A';
}

export interface AgentSummary {
  id: AgentId;
  displayName: string;
  provider: string;
  model: string;
  role: string;
  capabilities: string[];
  status: AgentStatus;
  phase?: PhaseName;
  persona?: PersonaProfile;
  presentation?: AgentPresentation;
  currentTask?: string;
  activeTool?: string;
  contextPct?: string;
  contextUsed?: string;
  contextMax?: string;
  queueDepth?: number;
  sessionTokens?: string;
}

export interface AgentDetail extends AgentSummary {
  input: string;
  output: string;
  cached: string;
  remaining: string;
  inPct: string;
  outPct: string;
  cachePct: string;
  activity: ActivityItem[];
  metrics: MetricItem[];
  runs: RunHistoryItem[];
  allowance: AllowanceItem[];
  capacity: string;
  reset: string;
  resetNote: string;
  crawlCode?: string;
  frameLog?: string;
  traceId?: string;
}

export interface ArtifactTrust {
  status: "verified" | "unverified" | "not_applicable";
  kind: "path_containment" | "git_reference" | "none";
  scope: "hermes_run_root" | "target_repository" | "external" | "unknown" | string;
  detail?: string;
}

export interface ArtifactRef {
  id: string;
  type: string;
  label: string;
  ref: string;
  jobId?: string;
  phaseId?: string;
  trust?: ArtifactTrust;
  metadata?: Record<string, any>;
  createdAt?: string;
}

export interface Message {
  id: string;
  threadId: string;
  from: ActorRef;
  to: ActorRef[];
  kind: string; // 'handoff' | 'a2a' | 'review_request' | 'review_result' | 'correction_request' | 'correction_result' | 'verification_request' | 'verification_result' | 'status' | 'warning' | 'operator' | 'system'
  text: string;
  intent?: string;
  conversationId?: string;
  replyTo?: string;
  correlationId?: string;
  jobId?: string;
  phaseId?: string;
  artifactRefs?: ArtifactRef[];
  metadata?: Record<string, any>;
  createdAt: string;
}

export interface Thread {
  id: string;
  jobId?: string;
  title?: string;
  participants: ActorRef[];
  createdAt: string;
  updatedAt: string;
}

export interface MailboxEntry {
  messageId: string;
  recipientId: string;
  state: 'PENDING' | 'DELIVERED' | 'ACKNOWLEDGED';
  receivedAt: string;
  acknowledgedAt?: string | null;
  message?: Message;
}

export interface JobPhase {
  id: string;
  name: string;
  order: number;
  role: string;
  agentId?: AgentId;
  agentName?: string;
  status: PhaseStatus;
  attempt?: number;
  durationMs?: number;
  startedAt?: string;
  completedAt?: string;
  commitSha?: string;
  changedFilesCount?: number;
  detail?: string;
  meta?: string;
  /** Ids of the phases this one waits for, as Hermes reports them. */
  dependencies?: string[];
}

export interface Job {
  id: string;
  sprintId?: string;
  title: string;
  repository: string;
  branch?: string;
  priority?: Priority | string;
  status: JobStatus;
  currentPhase?: string;
  assignedAgentIds: AgentId[];
  estimatedTokens?: string;
  estimatedTime?: string;
  createdAt?: string;
  startedAt?: string;
  completedAt?: string;
  progress?: number;
  budget?: string;
  policy?: string;
  phases?: JobPhase[];
  blockedReason?: any;
  repairCount?: number;
  replanCount?: number;
  tasks?: any[];
  observations?: any[];
}

export interface ChangedFile {
  mark: 'A' | 'M' | 'D';
  path: string;
  add: string;
  del: string;
  byActorId: string;
  byDisplayName: string;
}

export interface JobRetryItem {
  attempt: number;
  phase: PhaseName;
  status: 'passed' | 'failed';
  note?: string;
}

export interface JobTokenBreakdown {
  agentId: AgentId;
  agentName: string;
  phase: PhaseName;
  tokensFormatted: string;
  color?: string;
  percentage?: number;
}

export interface JobDetail extends Job {
  phases?: JobPhase[];
  executionGraph: PipelineStep[];
  changedFiles?: ChangedFile[];
  testSummary?: {
    total?: number;
    passed: number;
    skipped?: number;
    failed: number;
    duration?: string;
    durationMs?: number;
    rawLog?: string;
  };
  /** Undefined when Hermes reports no attempt history; never a fixed or invented list. */
  retryHistory?: JobRetryItem[];
  /** Not reported by the HTTP API. Only mock fixtures carry these. */
  retriesUsed?: number;
  maxRetries?: number;
  tokenBreakdown?: JobTokenBreakdown[];
  artifacts?: ArtifactRef[];
  errors?: any[];
  /** Raw verification result from Hermes (status/results); null when none was recorded. */
  verification?: unknown;
}

export interface PipelineStep {
  id: string;
  jobId?: string;
  phase: PhaseName;
  agentId?: AgentId;
  agentName?: string;
  task: string;
  meta: string;
  state: PipelineStepState;
  note?: string;
  mark?: string;
  title?: string;
  eta?: string;
  duration?: string;
  activeTool?: string;
  tokens?: string;
  attempt?: number;
}

export interface TraceEvent {
  id: string;
  ts: string;
  rawTs: number;
  source: ActorRef;
  kind: string;
  detail: string;
  dur: string;
  /** Real nulls from Hermes are kept as null, not turned into undefined. */
  jobId?: string | null;
  taskId?: string | null;
  runId?: string | null;
  actorId?: string | null;
  metadata?: Record<string, any>;
  /**
   * Where a job-history event came from. `stored` is the canonical durable envelope; `bus` is the in-memory
   * event bus fallback, which does not survive a restart. Live SSE and the global buffer leave this unset.
   */
  origin?: 'stored' | 'bus';
}

export interface ProviderQuota {
  id: string;
  name: string;
  color: string;
  pct: string;
  tag: 'EXACT' | 'ESTIMATED' | 'UNKNOWN';
  window: string;
  left: string;
  capacity: string;
  reset: string;
  resetTag: string;
  conf: string;
  basis: string;
  opacity: string;
}

export interface ProjectionItem {
  id: string;
  task: string;
  est: string;
  w: string;
  wLow: string;
  color: string;
  conf: 'high' | 'medium' | 'low';
}

export interface SettingItem {
  label: string;
  value: string;
  color?: string;
}

export interface OverviewTelemetry {
  runningJobsCount: number;
  queuedJobsCount: number;
  blockedJobsCount: number;
  /** null when it cannot be counted honestly (e.g. a failed job has no completedAt). */
  failed24hCount: number | null;
  /** Number of jobs the counts were derived from (GET /jobs returns at most its default limit). */
  sampleSize: number;
  tokensToday: string;
  estSpendToday: string;
  /** null: Hermes exposes no sprint budget, so no percentage can be computed. */
  sprintBudgetUsedPct: number | null;
}

export interface SendMessageRequest {
  threadId: string;
  to?: string[];
  kind?: string;
  text: string;
  intent?: string;
  conversationId?: string;
  replyTo?: string;
  correlationId?: string;
}

// Phase 7: Capability & Delegation Types
export interface Capability {
  id: string;
  description?: string;
  tags?: string[];
  metadata?: Record<string, any>;
}

export interface CapabilityRef {
  id: string;
  proficiency?: number | string;
  metadata?: Record<string, any>;
}

export interface DelegationRequest {
  id?: string;
  requester?: ActorRef;
  task: string;
  requiredCapabilities: string[];
  preferredActors?: string[];
  excludedActors?: string[];
  jobId?: string;
  threadId?: string;
  conversationId?: string;
  parentMessageId?: string;
  parentTaskId?: string;
  allowSubagent?: boolean;
  allowTools?: boolean;
  maxDepth?: number;
  metadata?: Record<string, any>;
}

export interface DelegationDecision {
  requestId: string;
  selectedActorId?: string;
  status: 'selected' | 'no_match' | 'rejected' | 'limit_reached' | string;
  reason?: string;
  rejectedReasons?: Record<string, string>;
  requiredCapabilities: string[];
  matchedCapabilities: string[];
  missingCapabilities: string[];
  metadata?: Record<string, any>;
}

export interface TaskAssignment {
  taskId: string;
  ownerActorId: string;
  task: string;
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled' | string;
  delegatedBy?: string;
  parentTaskId?: string;
  requiredCapabilities?: string[];
  jobId?: string;
  threadId?: string;
  conversationId?: string;
  createdAt?: string;
  completedAt?: string;
  artifactRefs?: ArtifactRef[];
  metadata?: Record<string, any>;
}

export interface ToolProfile {
  id: string;
  displayName: string;
  capabilities: string[];
  inputSchema?: Record<string, any>;
  outputSchema?: Record<string, any>;
  timeoutSeconds?: number;
  metadata?: Record<string, any>;
}

export interface ToolInvocationRequest {
  id?: string;
  toolId: string;
  args: Record<string, any>;
  requester?: ActorRef;
  jobId?: string;
  threadId?: string;
  conversationId?: string;
  parentMessageId?: string;
  timeoutSeconds?: number;
  metadata?: Record<string, any>;
}

export interface ToolInvocationResult {
  requestId: string;
  toolId: string;
  status: 'success' | 'failed' | 'rejected' | 'timeout' | string;
  output?: any;
  artifactRefs?: ArtifactRef[];
  error?: string;
  metadata?: Record<string, any>;
}

export interface SubagentProfile {
  id: string;
  parentAgentId: string;
  capabilities: string[];
  task: string;
  displayName?: string;
  depth?: number;
  ephemeral?: boolean;
  metadata?: Record<string, any>;
}

// D-009 Execution visibility (Hermes -> LysControl). Source of truth: Hermes-lab .agent/DECISIONS.md, D-009.
export type ExecutionBackendName = string; // 'subprocess' | 'herdr' | 'openrig' | open string

export type ExecutionResourceKind = 'seat' | 'pane' | 'process' | string;

export type ExecutionResourceState = 'acquiring' | 'ready' | 'running' | 'idle' | 'releasing' | 'failed';

export type ExecutionEventKind =
  | 'execution.started'
  | 'execution.resource_acquired'
  | 'execution.resource_ready'
  | 'execution.running'
  | 'execution.finished'
  | 'execution.failed'
  | 'execution.cancelled'
  | 'execution.resource_pooled'
  | 'execution.resource_released'
  | 'execution.release_failed';

export interface ExecutionResourceRef {
  kind: ExecutionResourceKind;
  id: string;
  label: string;
}

/** `metadata` of an `execution.*` TraceEvent. Every field is optional except backend and executionId. */
export interface ExecutionEventMetadata {
  backend: ExecutionBackendName;
  executionId: string;
  resource?: ExecutionResourceRef;
  reused?: boolean;
  generation?: string;
  rigId?: string;
  sessionName?: string;
  nodeId?: string;
  expiresAt?: string;
  errorCode?: string;
  error?: string;
  durationMs?: number;
}

export interface ExecutionBackendStatus {
  name: ExecutionBackendName;
  available: boolean;
  detail: string;
}

export interface ExecutionResource {
  backend: ExecutionBackendName;
  kind: ExecutionResourceKind;
  id: string;
  label: string;
  state: ExecutionResourceState;
  jobId?: string | null;
  taskId?: string | null;
  executionId?: string | null;
  since: string;
  expiresAt: string | null;
  /** Free-form per-backend details (reused, generation, rigId, errorCode, error, ...). */
  details: Record<string, any>;
}

export interface OpenRigLedger {
  owners: number;
  rigIds: string[];
}

export interface OpenRigExecutionStatus {
  daemon: 'up' | 'down' | 'unknown';
  ledger: OpenRigLedger;
}

/** GET /execution. Initial state; `execution.*` events are applied on top of it. */
export interface ExecutionSnapshot {
  backends: ExecutionBackendStatus[];
  resources: ExecutionResource[];
  openrig: OpenRigExecutionStatus | null;
  /** Epoch seconds (same clock as event rawTs). Events at or before it are already reflected. */
  takenAt?: number;
}

// ---------------------------------------------------------------------------
// M2 real-data DTOs. Field names are camelCase; nulls are real nulls from Hermes.
// ---------------------------------------------------------------------------

/** Source of a usage snapshot as Hermes labels it (runtime/capacity.py UsageSnapshot.source). */
export type UsageSource = 'provider_reported' | 'hermes_estimated' | 'unknown';

export interface UsageSnapshotView {
  source: UsageSource | string;
  observedAt: string | null;
  modelId: string | null;
  actorId: string | null;
  inputTokens: number | null;
  outputTokens: number | null;
  cachedTokens: number | null;
  tokensUsed: number | null;
  requestsUsed: number | null;
  requestsRemaining: number | null;
  requestLimit: number | null;
  tokensRemaining: number | null;
  tokenLimit: number | null;
  contextWindow: number | null;
  contextUsed: number | null;
  resetAt: string | null;
}

export interface ProviderTelemetry {
  providerId: string;
  status: string;
  statusReason: string | null;
  totalRequests: number;
  successCount: number;
  failureCount: number;
  /** null when no request has been made, because no rate can be stated. */
  successRate: number | null;
  throttlingCount: number;
  failureBreakdown: Record<string, number>;
  usage: UsageSnapshotView | null;
}

/** GET /capacity/telemetry. Totals are counted since the runtime process started; they are not daily totals. */
export interface CapacityTelemetry {
  timestamp: string | null;
  summary: {
    totalProviders: number | null;
    totalRequests: number | null;
    totalFailures: number | null;
    totalThrottlingEvents: number | null;
    totalTokens: number | null;
    inputTokens: number | null;
    outputTokens: number | null;
    cachedTokens: number | null;
  } | null;
  providers: ProviderTelemetry[];
  jobsTracked: number | null;
}

/** One usage window of an agent, as computed by GET /capacity/limits. */
export interface AgentLimitWindow {
  label: string;
  usedPct: number | null;
  leftPct: number | null;
  resetsAt: string | null;
  resetsInSeconds: number;
}

/** 'unknown' when the record has neither limit windows nor a funded balance. */
export type AgentLimitStatus = 'ok' | 'warn' | 'alarm' | 'unknown';

/** One agent in GET /capacity/limits. Percentages are computed by the backend. */
export interface AgentLimit {
  id: string;
  name: string;
  plan: string;
  ready: boolean;
  stale: boolean;
  status: AgentLimitStatus | string;
  usedPct: number | null;
  leftPct: number | null;
  resetsAt: string | null;
  resetsInSeconds: number;
  windows: AgentLimitWindow[];
  updatedAt: string | null;
  authHelp: string;
}

export interface AgentLimitsReport {
  timestamp: string | null;
  agents: AgentLimit[];
}

/** GET /jobs/{id}/telemetry. Zero means no usage was tracked for the job, not proof that none was spent. */
export interface JobTokenTelemetry {
  jobId: string;
  inputTokens: number;
  outputTokens: number;
  cachedTokens: number;
  totalTokens: number;
  /** Agent-reported cost in USD; null when no agent of the job reported one (Codex reports none). */
  costUsd: number | null;
  /** One row per agent run, in the order they finished. Empty for jobs from before per-task usage. */
  tasks: TaskUsage[];
}

/** Token use of one agent run on one task, from GET /jobs/{id}/telemetry. */
export interface TaskUsage {
  taskId: string;
  actorId: string | null;
  attempt: number | null;
  status: string | null;
  totalTokens: number;
  costUsd: number | null;
}

export interface TaskNode {
  taskId: string;
  jobId: string;
  description: string;
  status: string;
  dependencies: string[];
  requiredCapabilities: string[];
  assignedActor: string | null;
  parentTaskId: string | null;
  createdAt: string | null;
  startedAt: string | null;
  completedAt: string | null;
  attempt: number;
  maxAttempts: number | null;
  error: unknown;
  supersededBy: string | null;
  artifactRefs: ArtifactRef[];
}

export interface AgentRun {
  runId: string;
  jobId: string;
  taskId: string;
  actorId: string;
  status: string;
  attempt: number;
  startedAt: string | null;
  finishedAt: string | null;
  exitReason: string | null;
  error: unknown;
  artifactRefs: ArtifactRef[];
}

export interface JobObservation {
  observationId: string;
  jobId: string;
  kind: string;
  content: string;
  taskId: string | null;
  actorId: string | null;
  source: string | null;
  confidence: number | null;
  createdAt: string | null;
}

// --------------------------------------------------------------------------
// M8 Agent Model Registry DTOs (GET /agents/models, PUT /agents/{id}/model)
// --------------------------------------------------------------------------

export type AgentEffort = 'minimal' | 'low' | 'medium' | 'high' | 'xhigh';

export type LastUsedSource = 'phase' | 'config' | 'cli-default';

export interface AgentConfiguredModel {
  default: string | null;
  effort?: AgentEffort | string | null;
}

export interface AgentLastUsedModel {
  model: string;
  effort?: AgentEffort | string | null;
  source: LastUsedSource | string;
}

export interface AgentModelConfig {
  configured: AgentConfiguredModel | null;
  allowed: string[];
  lastUsed: AgentLastUsedModel | null;
}

export type AgentModelsMap = Record<string, AgentModelConfig>;

export interface SetAgentModelRequest {
  model: string;
  effort?: AgentEffort | string | null;
}

export interface SetAgentModelResponse {
  default: string;
  effort: string | null;
}

/** One task of a finished run, as the review lists it. */
export interface ReviewTask {
  id: string;
  role: string;
  agent: string;
  status: string;
}

/** The last passing check of a finished run: its summary and the findings it reported. */
export interface ReviewVerdict {
  task: string;
  summary: string | null;
  findings: string[];
}

/** A completed goal-planned run waiting for (or past) human review, from GET /reviews. */
export interface RunReview {
  jobId: string;
  goal: string;
  branch: string;
  repairs: number;
  tasks: ReviewTask[];
  verdict: ReviewVerdict | null;
  costUsd: number | null;
  totalTokens: number;
  /** null when Hermes could not open the pull request (no remote, gh missing, or turned off). */
  prUrl: string | null;
  finishedAt: string | null;
}
