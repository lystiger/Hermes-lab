import { Job, JobDetail, PipelineStep, ChangedFile } from '../types';

export const MOCK_JOBS: Job[] = [
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
  },
  {
    id: '#144',
    priority: 'P1',
    title: 'Authentication refactor — session adapter',
    repository: 'moveinmate/backend',
    assignedAgentIds: ['gemini', 'claude'],
    estimatedTokens: '~40–55k',
    estimatedTime: '~21 min',
    status: 'BLOCKED',
    createdAt: '10:30'
  },
  {
    id: '#145',
    priority: 'P1',
    title: 'Queue scheduler regression tests',
    repository: 'hermes-lab',
    assignedAgentIds: ['codex'],
    estimatedTokens: '~22k',
    estimatedTime: '~7 min',
    status: 'QUEUED',
    createdAt: '10:25'
  },
  {
    id: '#146',
    priority: 'P2',
    title: 'Frontend accessibility audit pass 2',
    repository: 'unigreen/web',
    assignedAgentIds: ['gemini', 'codex'],
    estimatedTokens: '~14k',
    estimatedTime: '~6 min',
    status: 'QUEUED',
    createdAt: '10:20'
  },
  {
    id: '#147',
    priority: 'P2',
    title: 'Memory compaction policy rewrite',
    repository: 'lyscontrol/core',
    assignedAgentIds: ['claude', 'codex'],
    estimatedTokens: '~27k',
    estimatedTime: '~14 min',
    status: 'QUEUED',
    createdAt: '10:15'
  },
  {
    id: '#148',
    priority: 'P3',
    title: 'Redis client compatibility matrix',
    repository: 'moveinmate/backend',
    assignedAgentIds: ['gemini', 'claude', 'codex'],
    estimatedTokens: '~16–34k',
    estimatedTime: '~18 min',
    status: 'QUEUED',
    createdAt: '10:10'
  },
  {
    id: '#141',
    priority: 'P1',
    title: 'Frontend accessibility audit',
    repository: 'unigreen/web',
    assignedAgentIds: ['gemini', 'codex'],
    estimatedTokens: '34.9k',
    estimatedTime: '09:12',
    status: 'COMPLETED',
    createdAt: '09:40',
    completedAt: '10:12'
  },
  {
    id: '#136',
    priority: 'P2',
    title: 'Hermes phase policy rewrite',
    repository: 'hermes-lab',
    assignedAgentIds: ['claude'],
    estimatedTokens: '44.1k',
    estimatedTime: '07:18',
    status: 'CANCELLED',
    createdAt: '09:15'
  }
];

export const MOCK_PIPELINE: PipelineStep[] = [
  {
    id: '#142',
    phase: 'BUILD',
    agentId: 'gemini',
    agentName: 'Gemini',
    task: 'Move VehicleStateStore to Redis',
    meta: '30.4k · 06:12',
    state: 'COMPLETED',
    note: 'implementation complete',
    mark: '✓'
  },
  {
    id: '#142',
    phase: 'HARDEN',
    agentId: 'claude',
    agentName: 'Claude',
    task: 'Review store contract — TTL, read-after-write',
    meta: '02:14',
    state: 'RUNNING',
    note: 'reviewing store contract',
    mark: '●'
  },
  {
    id: '#142',
    phase: 'VERIFY',
    agentId: 'codex',
    agentName: 'Codex',
    task: '186 tests · mypy strict · ruff',
    meta: 'staged ~19k',
    state: 'QUEUED',
    note: 'waiting for handoff',
    mark: '○'
  },
  {
    id: '#142',
    phase: 'COMPLETE',
    agentId: 'elysia',
    agentName: 'Elysia',
    task: 'Merge + report telemetry',
    meta: '',
    state: 'IDLE',
    note: 'merge + report'
  },
  {
    id: '#143',
    phase: 'BUILD',
    agentId: 'gemini',
    agentName: 'Gemini',
    task: 'Fix production CI — flaky worker teardown',
    meta: '~18–30k',
    state: 'CLAIMED'
  },
  {
    id: '#144',
    phase: 'BUILD',
    agentId: 'gemini',
    agentName: 'Gemini',
    task: 'Authentication refactor — session adapter',
    meta: 'waiting on repo lock',
    state: 'BLOCKED'
  }
];

export const MOCK_CHANGED_FILES: ChangedFile[] = [
  { mark: 'A', path: 'src/state/redis_store.py', add: '+184', del: '−0', byActorId: 'gemini', byDisplayName: 'Gemini' },
  { mark: 'M', path: 'src/state/store.py', add: '+22', del: '−96', byActorId: 'gemini', byDisplayName: 'Gemini' },
  { mark: 'M', path: 'src/state/__init__.py', add: '+4', del: '−2', byActorId: 'gemini', byDisplayName: 'Gemini' },
  { mark: 'A', path: 'tests/state/test_redis_store.py', add: '+141', del: '−0', byActorId: 'gemini', byDisplayName: 'Gemini' },
  { mark: 'M', path: 'tests/state/test_migration.py', add: '+38', del: '−11', byActorId: 'gemini', byDisplayName: 'Gemini' },
  { mark: 'M', path: 'docs/adr/0007-state.md', add: '+61', del: '−4', byActorId: 'claude', byDisplayName: 'Claude' },
  { mark: 'M', path: 'compose.yaml', add: '+9', del: '−0', byActorId: 'gemini', byDisplayName: 'Gemini' }
];

export const MOCK_ACTIVE_JOB_DETAIL: JobDetail = {
  id: '#142',
  priority: 'P1',
  title: 'Redis State Migration',
  repository: 'moveinmate/backend',
  branch: 'feat/redis-state',
  status: 'RUNNING',
  assignedAgentIds: ['gemini', 'claude', 'codex'],
  startedAt: '10:38',
  budget: '80k',
  policy: 'serial · retry 3',
  phases: [],
  executionGraph: MOCK_PIPELINE.slice(0, 4),
  changedFiles: MOCK_CHANGED_FILES,
  testSummary: {
    passed: 184,
    skipped: 2,
    failed: 0,
    duration: '18.4s',
    rawLog: `tests/state/test_redis_store.py ......... [ 62%]\ntests/state/test_migration.py ....s.... [ 91%]\ntests/state/test_ttl.py ....s [100%]\n186 collected · 184 passed · 2 skipped in 18.4s`
  },
  retryHistory: [
    { attempt: 1, phase: 'BUILD', status: 'failed', note: 'redis connection refused in sandbox; retried with local container' },
    { attempt: 2, phase: 'BUILD', status: 'passed', note: 'container connection successful' }
  ],
  retriesUsed: 1,
  maxRetries: 3,
  tokenBreakdown: [
    { agentId: 'gemini', agentName: 'Gemini', phase: 'BUILD', tokensFormatted: '30.4k', color: '#5B8CFF', percentage: 38 },
    { agentId: 'claude', agentName: 'Claude', phase: 'HARDEN', tokensFormatted: '13.7k', color: '#D9A05B', percentage: 17 },
    { agentId: 'codex', agentName: 'Codex', phase: 'VERIFY', tokensFormatted: '~19k', color: '#4EC9A0', percentage: 0 }
  ]
};
