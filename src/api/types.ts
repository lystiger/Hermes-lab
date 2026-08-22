export type AgentName = 'Gemini' | 'Claude' | 'Codex' | 'Elysia';

export type JobStatus = 'QUEUED' | 'CLAIMED' | 'RUNNING' | 'VERIFYING' | 'BLOCKED' | 'FAILED' | 'COMPLETE' | 'COMPLETED' | 'CANCELLED';

export type Priority = 'P0' | 'P1' | 'P2' | 'P3';

export type PhaseName = 'BUILD' | 'HARDEN' | 'VERIFY' | 'COMPLETE';

export interface ActivityItem {
  op: 'READ' | 'WRITE' | 'RUN' | 'STAGE' | 'NOTE' | 'IDLE';
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

export interface AgentData {
  id: string;
  name: AgentName;
  model: string;
  provider: string;
  role: string;
  status: 'RUNNING' | 'WAITING' | 'IDLE' | 'OFFLINE';
  phase: PhaseName;
  task: string;
  tool: string;
  color: string;
  ctxUsed: string;
  ctxMax: string;
  ctxPct: string;
  input: string;
  output: string;
  cached: string;
  remaining: string;
  inPct: string;
  outPct: string;
  cachePct: string;
  avatarUrl: string;
  activity: ActivityItem[];
  metrics: MetricItem[];
  runs: RunHistoryItem[];
  allowance: AllowanceItem[];
  capacity: string;
  reset: string;
  resetNote: string;
  crawlCode: string;
  frameLog: string;
  traceId: string;
  depth: number;
}

export interface JobItem {
  id: string;
  prio: Priority;
  task: string;
  repo: string;
  branch?: string;
  chain: AgentName[];
  tokens: string;
  time: string;
  status: JobStatus;
  started?: string;
  elapsed?: string;
  budget?: string;
  policy?: string;
  testLog?: string;
}

export interface PipelineStep {
  id: string;
  phase: PhaseName;
  agent: AgentName | '—';
  task: string;
  meta: string;
  state: 'COMPLETE' | 'RUNNING' | 'QUEUED' | 'CLAIMED' | 'BLOCKED';
  note?: string;
}

export interface ChangedFile {
  mark: 'A' | 'M' | 'D';
  path: string;
  add: string;
  del: string;
  by: AgentName;
}

export interface TraceEvent {
  id: string;
  ts: string;
  rawTs: number;
  agent: string;
  kind: string;
  detail: string;
  dur: string;
  job: string;
}

export interface ProviderQuota {
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
