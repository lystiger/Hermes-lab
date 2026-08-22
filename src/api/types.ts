// Generic Agent Identity (No closed unions)
export type AgentId = string;

export type AgentStatus = 'RUNNING' | 'WAITING' | 'IDLE' | 'OFFLINE' | 'BUSY' | 'ERROR';

export type Priority = 'P0' | 'P1' | 'P2' | 'P3';

export type JobStatus = 'QUEUED' | 'CLAIMED' | 'RUNNING' | 'VERIFYING' | 'BLOCKED' | 'FAILED' | 'COMPLETE' | 'COMPLETED' | 'CANCELLED';

export type PhaseName = 'BUILD' | 'HARDEN' | 'VERIFY' | 'COMPLETE' | 'REVIEW' | 'CUSTOM';

export type ActorKind = 'agent' | 'system' | 'runtime' | 'tool';

export interface ActorRef {
  id: string;
  kind: ActorKind;
  displayName: string;
  accentColor?: string;
}

export interface AgentPresentation {
  displayName: string;
  avatarUrl?: string;
  accentColor?: string;
  animationProfile?: 'quick' | 'relaxed' | 'slow' | 'steady' | 'none';
  sigil?: string;
  code?: string;
  badge?: string;
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

export interface Job {
  id: string;
  priority: Priority;
  title: string;
  repository: string;
  branch?: string;
  status: JobStatus;
  assignedAgentIds: AgentId[];
  estimatedTokens?: string;
  estimatedTime?: string;
  createdAt?: string;
  startedAt?: string;
  completedAt?: string;
  budget?: string;
  policy?: string;
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
  executionGraph: PipelineStep[];
  changedFiles: ChangedFile[];
  testSummary?: {
    passed: number;
    skipped: number;
    failed: number;
    duration: string;
    rawLog: string;
  };
  retryHistory: JobRetryItem[];
  retriesUsed: number;
  maxRetries: number;
  tokenBreakdown: JobTokenBreakdown[];
}

export interface PipelineStep {
  id: string;
  phase: PhaseName;
  agentId?: AgentId;
  agentName?: string;
  task: string;
  meta: string;
  state: 'COMPLETE' | 'RUNNING' | 'QUEUED' | 'CLAIMED' | 'BLOCKED' | 'idle';
  note?: string;
  mark?: string;
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
  resetTag: 'EXACT' | 'EST' | 'N/A';
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

// Future-Proof Messaging Contracts (Contracts Only - No A2A implementation yet)
export type ArtifactType = 'git_commit' | 'git_diff' | 'file' | 'test_report' | 'log' | 'generic';

export interface ArtifactRef {
  id: string;
  type: ArtifactType;
  ref: string;
  label?: string;
}

export interface Message {
  id: string;
  threadId: string;
  from: ActorRef;
  to: ActorRef[];
  text: string;
  intent?: string;
  jobId?: string;
  artifactRefs?: ArtifactRef[];
  createdAt: string;
}

export interface Thread {
  id: string;
  jobId?: string;
  participants: ActorRef[];
  createdAt: string;
  updatedAt: string;
}
