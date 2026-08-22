// Generic Agent Identity (No closed unions)
export type AgentId = string;

export type AgentStatus = 'RUNNING' | 'WAITING' | 'IDLE' | 'OFFLINE' | 'BUSY' | 'ERROR';

export type Priority = 'P0' | 'P1' | 'P2' | 'P3';

export type JobStatus =
  | 'QUEUED'
  | 'PREPARING'
  | 'RUNNING'
  | 'BLOCKED'
  | 'FAILED'
  | 'COMPLETED'
  | 'CANCELLED'
  | 'CLAIMED'
  | 'VERIFYING';

export type PhaseStatus =
  | 'PENDING'
  | 'PREPARING'
  | 'RUNNING'
  | 'SUCCEEDED'
  | 'FAILED'
  | 'SKIPPED'
  | 'CANCELLED';

export type PipelineStepState = 'COMPLETED' | 'RUNNING' | 'QUEUED' | 'CLAIMED' | 'BLOCKED' | 'IDLE';

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
  changedFiles: ChangedFile[];
  testSummary?: {
    total?: number;
    passed: number;
    skipped?: number;
    failed: number;
    duration?: string;
    durationMs?: number;
    rawLog?: string;
  };
  retryHistory: JobRetryItem[];
  retriesUsed: number;
  maxRetries: number;
  tokenBreakdown: JobTokenBreakdown[];
  artifacts?: ArtifactRef[];
  errors?: any[];
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
  jobId?: string;
  metadata?: Record<string, any>;
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
  failed24hCount: number;
  tokensToday: string;
  estSpendToday: string;
  sprintBudgetUsedPct: number;
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
